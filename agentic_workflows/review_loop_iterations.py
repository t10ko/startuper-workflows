"""Mechanical enforcement of `code-review-fix-loop`'s iteration cap.

The skill has carried `--max-iterations` (default 5) and states plainly that
a run stopping on the cap has NOT earned the "clean" claim. Measured over
seven days in its origin repo, the cap did not hold: 64 iterations across
6 sessions, a mean of 10.7, four sessions past 5, and only three of six
reaching a clean exit.

Prose in a markdown file is not enforcement. Of the hook events available,
only `PreToolUse` can refuse a call -- `SubagentStart` is context-only by
contract and cannot decline a spawn. So the cap is applied where the
dispatch itself happens.

This module owns the decision and holds no I/O, so the rule is testable
without a filesystem. The `limit_review_loop_iterations` hook reads and
writes the ledger around it.

The same ledger also carries the fixer redispatch cap for the review-fix
phase: at most two fresh fixers per review-fix batch per loop iteration,
never reset by the idle gap. There the enforcement seam is the
orchestrator's redispatch decision, not a hook.

Known limits, stated rather than discovered later:

- A session may invoke the loop more than once, and nothing in the dispatch
  payload marks a run boundary. An idle gap is the only available signal, so
  a genuine second run started inside `RUN_IDLE_RESET` is refused, and a
  single run that stalls past it silently gets a fresh budget.
- Counting one agent type is evadable: a coordinator that stopped
  dispatching the marker while continuing other dimensions would not be
  counted. Counting rewrites of the diff snapshot would be exact, but that
  file is written through a shell redirect no file-write matcher observes.
- This bounds iteration COUNT. It does not make the loop converge, and
  `root-cause-before-guardrails` applies: if each round of fixes introduces
  fresh findings, the structural inability to reach a confirming clean pass
  is the real defect and this only bounds its cost.
"""

from __future__ import annotations

import datetime
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentic_workflows.file_io import write_text_atomic

# `code-review-fix-loop`'s own documented default. One dispatch of the
# always-on first dimension marks one loop iteration.
MAX_ITERATIONS = 5

ITERATION_MARKER_AGENT = "code-reviewer"

# Consecutive iterations of one run follow each other in minutes; a second
# invocation of the skill follows a human turn. Twenty minutes separates
# those two populations without being so long that an ordinary follow-up run
# is caught by it.
RUN_IDLE_RESET = datetime.timedelta(minutes=20)

# A BLOCKED review-fix batch is re-dispatched as a fresh fixer, but a third
# BLOCKED escalates to the human or defers the batch's remaining findings to
# the next iteration -- a fourth fixer is never dispatched.
MAX_FIXER_REDISPATCHES = 2

_DENIAL = (
    f"code-review-fix-loop has already run {MAX_ITERATIONS} iterations in this "
    f"session (its own --max-iterations default). Stop looping now and write "
    f"the Report. This run has NOT earned the 'clean' claim -- the confirming "
    f"full pass never ran, so say so explicitly and list the findings still "
    f"outstanding. Do not dispatch further review dimensions for this run."
)


def _require_aware(value: datetime.datetime, name: str) -> datetime.datetime:
    """AwareDatetime semantics: a naive timestamp is rejected at load."""
    if not isinstance(value, datetime.datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value


@dataclass(frozen=True)
class ReviewLoopLedger:
    """How many iterations this session has run, and when the last one was.

    `last_dispatch_at` exists only to detect a run boundary; it is advanced
    by the marker agent alone, so an unrelated later dispatch cannot hold a
    spent run open forever. It is typed aware so a tampered naive timestamp
    is rejected at load by the usual `ValueError` path instead of crashing
    the idle-gap subtraction mid-decision; corrupt ledger degrades loudly,
    not silently.
    """

    iterations: int
    last_dispatch_at: datetime.datetime
    # Fresh-fixer redispatches per review-fix batch within the current loop
    # iteration. Keys are the string form of the integer `FixBatch.batch_id`
    # -- JSON object keys must be strings -- and the validator below rejects
    # any key that is not that exact form, so no hand-edited second spelling
    # of one batch can load and grant it a second budget. Counts are
    # non-negative: a negative value fails validation at load rather than
    # granting extra budget. Cleared only by a genuine iteration advance --
    # never by the idle reset, so a stalled run cannot regain the budget.
    fixer_redispatches: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.iterations, int) or isinstance(
            self.iterations, bool
        ):
            raise ValueError("iterations must be an integer")
        if self.iterations < 0:
            raise ValueError("iterations must be >= 0")
        _require_aware(self.last_dispatch_at, "last_dispatch_at")
        mismatched = [
            key
            for key in self.fixer_redispatches
            if not isinstance(key, str)
            or not key.isdecimal()
            or str(int(key)) != key
        ]
        if mismatched:
            raise ValueError(
                f"fixer_redispatches keys {mismatched} are not the canonical "
                f"string form of their integer batch ids, the one form "
                f"`str(batch_id)` produces; a hand-edited spelling must fail "
                f"at load rather than silently unbind a batch's redispatch "
                f"budget."
            )
        for key, count in self.fixer_redispatches.items():
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise ValueError(
                    f"fixer_redispatches[{key!r}] must be a non-negative integer"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "iterations": self.iterations,
            "last_dispatch_at": self.last_dispatch_at.isoformat(),
            "fixer_redispatches": dict(self.fixer_redispatches),
        }

    @classmethod
    def from_payload(cls, payload: object) -> ReviewLoopLedger:
        """Validate one decoded ledger JSON object (extra keys forbidden)."""
        if not isinstance(payload, dict):
            raise ValueError("ledger must be a JSON object")
        allowed = {"iterations", "last_dispatch_at", "fixer_redispatches"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unknown ledger fields: {sorted(unknown)}")
        missing = {"iterations", "last_dispatch_at"} - set(payload)
        if missing:
            raise ValueError(f"missing ledger fields: {sorted(missing)}")
        redispatches = payload.get("fixer_redispatches", {})
        if not isinstance(redispatches, dict):
            raise ValueError("fixer_redispatches must be a JSON object")
        raw_at = payload["last_dispatch_at"]
        if not isinstance(raw_at, str):
            raise ValueError("last_dispatch_at must be an ISO datetime string")
        return cls(
            iterations=payload["iterations"],
            last_dispatch_at=datetime.datetime.fromisoformat(raw_at),
            fixer_redispatches=dict(redispatches),
        )


@dataclass(frozen=True)
class DispatchDecision:
    """Whether this dispatch proceeds, and the ledger to persist either way."""

    allowed: bool
    ledger: ReviewLoopLedger
    reason: str = ""


def decide_dispatch(
    ledger: ReviewLoopLedger | None,
    agent_type: str,
    *,
    now: datetime.datetime,
) -> DispatchDecision:
    """Allow or refuse one agent dispatch, and return the ledger to store.

    Everything that is not the iteration marker passes through untouched:
    each loop iteration dispatches several dimensions, and counting them all
    would divide the budget by however many happened to fire.
    """
    _require_aware(now, "now")
    if agent_type != ITERATION_MARKER_AGENT:
        keep = ledger or ReviewLoopLedger(iterations=0, last_dispatch_at=now)
        return DispatchDecision(allowed=True, ledger=keep)

    if ledger is None or now - ledger.last_dispatch_at >= RUN_IDLE_RESET:
        return DispatchDecision(
            allowed=True,
            # The idle reset starts a fresh run but deliberately carries the
            # redispatch counts: only a genuine iteration advance below may
            # clear them, or a stalled run would regain redispatch budget.
            ledger=ReviewLoopLedger(
                iterations=1,
                last_dispatch_at=now,
                fixer_redispatches=ledger.fixer_redispatches if ledger else {},
            ),
        )

    if ledger.iterations >= MAX_ITERATIONS:
        # Deliberately does NOT advance the count: a retried dispatch would
        # otherwise report a runaway iteration number that never ran.
        return DispatchDecision(allowed=False, ledger=ledger, reason=_DENIAL)

    # A genuine iteration advance also starts a fresh per-batch redispatch
    # budget: `fixer_redispatches` is deliberately not carried.
    return DispatchDecision(
        allowed=True,
        ledger=ReviewLoopLedger(iterations=ledger.iterations + 1, last_dispatch_at=now),
    )


def decide_fixer_redispatch(
    ledger: ReviewLoopLedger,
    batch_id: int,
) -> DispatchDecision:
    """Allow or refuse one fresh fixer on a BLOCKED review-fix batch.

    At most `MAX_FIXER_REDISPATCHES` per batch per iteration; a third BLOCKED
    escalates to the human or defers the batch's remaining findings to the
    next iteration's finding list instead. Mirrors `decide_dispatch`: a
    refusal does not advance the count, and the returned ledger is the
    caller's to persist around the redispatch.

    `batch_id` is the integer `FixBatch.batch_id` itself. Taking `int` (not
    `str`) makes the canonical ledger key a one-place normalization below:
    the string form exists only because JSON object keys must be strings,
    and a divergent spelling like `f"batch-{id}"` is unreachable at the
    signature, so one batch cannot silently hold two budgets.
    """
    key = str(batch_id)
    used = ledger.fixer_redispatches.get(key, 0)
    if used >= MAX_FIXER_REDISPATCHES:
        return DispatchDecision(
            allowed=False,
            ledger=ledger,
            reason=(
                f"batch {batch_id} has already had {MAX_FIXER_REDISPATCHES} "
                f"fresh-fixer redispatches this iteration. Do not dispatch a "
                f"fourth fixer: escalate the blocker to the human, or defer "
                f"the batch's remaining findings to the next iteration's "
                f"finding list."
            ),
        )
    return DispatchDecision(
        allowed=True,
        # Iteration and idle-clock state belong to the marker agent alone.
        ledger=ReviewLoopLedger(
            iterations=ledger.iterations,
            last_dispatch_at=ledger.last_dispatch_at,
            fixer_redispatches={**ledger.fixer_redispatches, key: used + 1},
        ),
    )


@dataclass(frozen=True)
class _LedgerFile:
    """Every session's ledger in one file, keyed by session id.

    Sessions never share a budget: two review loops running side by side are
    ordinary, and one exhausting the other's allowance would deny a run that
    had not iterated at all.
    """

    sessions: dict[str, ReviewLoopLedger] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessions": {
                session_id: ledger.to_dict()
                for session_id, ledger in self.sessions.items()
            }
        }

    @classmethod
    def from_payload(cls, payload: object) -> _LedgerFile:
        if not isinstance(payload, dict):
            raise ValueError("ledger file must be a JSON object")
        unknown = set(payload) - {"sessions"}
        if unknown:
            raise ValueError(f"unknown ledger-file fields: {sorted(unknown)}")
        raw_sessions = payload.get("sessions", {})
        if not isinstance(raw_sessions, dict):
            raise ValueError("sessions must be a JSON object")
        return cls(
            sessions={
                session_id: ReviewLoopLedger.from_payload(raw)
                for session_id, raw in raw_sessions.items()
            }
        )


def _read_file(path: Path) -> _LedgerFile:
    """Every ledger on disk, or an empty one.

    An absent file reads as empty. This runs as a hook on a live session: a
    bookkeeping file that lost a race must not take the session down with it.
    An EXISTING but unparsable ledger also reads as empty so the hook stays
    alive, but loudly: a stderr signal (the channel this hook already uses
    for denials) names the file and the reason, because read silently as
    empty, the next dispatch would reset the iteration count and restore the
    redispatch budget without a trace. Counting restarting from empty is the
    honest behavior once the signal is seen; the tampered budget itself is
    never honored.
    """
    if not path.is_file():
        return _LedgerFile()
    try:
        return _LedgerFile.from_payload(
            json.loads(path.read_text(encoding="utf-8"))
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        sys.stderr.write(
            f"review-loop iteration ledger at {path.as_posix()} is unreadable or "
            f"unparsable ({error}); it reads as empty for this dispatch, so "
            f"iteration counting restarts and the recorded budget is not honored.\n"
        )
        return _LedgerFile()


def load_ledger(path: Path, session_id: str) -> ReviewLoopLedger | None:
    """This session's ledger, or None when it has no recorded iterations."""
    return _read_file(path).sessions.get(session_id)


def store_ledger(path: Path, session_id: str, ledger: ReviewLoopLedger) -> None:
    """Record this session's ledger, preserving every other session's.

    Written atomically (sibling temp file + replace): a torn ledger here
    would self-inflict `_read_file`'s corrupt-ledger path on every later
    dispatch in this session.
    """
    merged = _read_file(path).sessions.copy()
    merged[session_id] = ledger
    write_text_atomic(path, json.dumps(_LedgerFile(sessions=merged).to_dict()))
