"""The one capacity authority for the per-run agent-worktree cap N.

The acquire CLI and the hook backstop both import this module so their
counting cannot diverge: one config read, one `git worktree list` parse,
one exemption derivation, and the two counting rules that share it -- the
global on-disk count (`capacity_snapshot`, the hook's raw-`worktree add`
backstop) and the per-run lease count (`run_capacity_view`, the cap the
acquire CLI enforces). Import-only and CLI-free, so a PreToolUse hook can
use it.

The cap is PER RUN (REQ-008, revised 2026-09-17): a run's group and
review-fix worktrees must not exceed N; other runs' worktrees -- leased or
not -- never count against a run, and the run's single integration
worktree is exempt. Leases carry the owning run's identity (`run_id`, the
acquiring run's branch name) and no timer: a live holder is never
auto-reclaimed, and freeing a slot is the owning run's explicit,
durability-gated release (REQ-013).

Fail-closed posture (REQ-007, REQ-011): every input the capacity decision
depends on -- the config file, git's listing, the lease ledger -- either
yields a usable value or raises `WorktreeCapacityError` naming the
undecidable input. There is no default anywhere: a default N would be a
second store, and a guessed count would silently unbound the cap. The CLI
maps that one error type to exit 2.

External inputs are injected, not reached for: `GitRunner` supplies the
porcelain listing (tests inject garbage to prove the fail-closed behavior
without a real repo), and config/records/ledger paths are parameters.
`plan_run_state` supplies the run-record parser the integration exemption
is derived from -- the exemption is read from the run's own record, never
from convention (REQ-007, EC-004).
"""

from __future__ import annotations

import datetime
import fcntl
import json
import shutil
import subprocess
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from agentic_workflows.file_io import write_text_atomic
from agentic_workflows.git_checkout_resolution import (
    AGENT_WORKTREE_ROOT,
    RESOLUTION_FAILURES,
)
from agentic_workflows.plan_run_paths import PLAN_RUNS_DIR
from agentic_workflows.plan_run_state import parse_plan_run_state

# The single machine-readable owner of N. Prose references this
# file; nothing restates the number.
CONFIG_PATH = Path(".agents/config.toml")

# Consumer-local override layer, resolved first when present. Lives OUTSIDE
# the `.agents` tree on purpose: a consumer's `.agents` may be a symlink into
# a shared checkout of this repo, and a local override written inside it
# would leak into every other consumer of that checkout.
LOCAL_CONFIG_PATH = Path(".agents.local.toml")

# The one key N lives under (spec section 21 discretion, named here so the
# CLI and the hook never hardcode the TOML shape).
WORKTREES_TABLE = "worktrees"
MAX_CONCURRENT_KEY = "max_concurrent"


class WorktreeCapacityError(ValueError):
    """A fail-closed refusal: some input the capacity decision depends on
    is missing, unreadable, or undecidable, and the message names it. The
    CLI maps this type to exit 2 (plan section 3(c)); it must never be
    caught into a guess."""


class GitRunner(Protocol):
    """Anything that can produce `git worktree list --porcelain` output for
    a repository. The injection seam that keeps the parse and every count
    decision testable without a real repo (and lets tests prove the
    fail-closed path with garbage input)."""

    def __call__(self, repo_root: Path, /) -> str: ...


@dataclass(frozen=True)
class WorktreeEntry:
    """One registered worktree: where it lives and which branch it holds."""

    path: Path
    branch: str


# ---------------------------------------------------------------------------
# Config: load N fail-closed, naming the config path (REQ-011).
# ---------------------------------------------------------------------------


def resolve_config_path(repo_root: Path) -> Path:
    """The config file a decision at `repo_root` reads: the consumer-local
    override layer when it exists, else the canonical `.agents/config.toml`.
    One lookup, shared by the acquire CLI and the hook backstop, so the two
    can never read different layers."""
    local = repo_root / LOCAL_CONFIG_PATH
    if local.is_file():
        return local
    return repo_root / CONFIG_PATH


def load_max_concurrent_worktrees(config_path: Path = CONFIG_PATH) -> int:
    """N, the maximum number of agent worktrees leased to one run at any
    moment (the run's integration worktree is exempt).

    Every malformed state -- absent file, unparsable TOML, missing table or
    key, non-integer, zero, negative -- raises instead of applying a
    default, because a default would be a second store of N (REQ-011). The
    message names the config path and key so the fix is one read away.
    """
    try:
        table = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise WorktreeCapacityError(
            f"{config_path.as_posix()} does not exist. The worktree cap N has "
            f"exactly one machine-readable owner: the [{WORKTREES_TABLE}] "
            f"table's {MAX_CONCURRENT_KEY} key in that file. Create it (for "
            f"example `[{WORKTREES_TABLE}]` / `{MAX_CONCURRENT_KEY} = 5`); "
            "no default is applied (REQ-011)."
        ) from None
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise WorktreeCapacityError(
            f"cannot read the worktree cap from {config_path.as_posix()}: {error}"
        ) from error

    worktrees = table.get(WORKTREES_TABLE)
    if not isinstance(worktrees, dict):
        raise WorktreeCapacityError(
            f"{config_path.as_posix()} has no [{WORKTREES_TABLE}] table; the "
            f"worktree cap N must be configured there as "
            f"`{MAX_CONCURRENT_KEY} = <positive whole number>` (REQ-011)."
        )
    value = worktrees.get(MAX_CONCURRENT_KEY)
    if isinstance(value, bool) or not isinstance(value, int):
        raise WorktreeCapacityError(
            f"`{WORKTREES_TABLE}.{MAX_CONCURRENT_KEY}` must be a whole number "
            f"in {config_path.as_posix()}, got {value!r} (REQ-011)."
        )
    if value < 1:
        raise WorktreeCapacityError(
            f"`{WORKTREES_TABLE}.{MAX_CONCURRENT_KEY}` must be at least 1 in "
            f"{config_path.as_posix()}, got {value!r} -- a non-positive cap "
            "cannot hold and must fail closed (REQ-011)."
        )
    return value


# ---------------------------------------------------------------------------
# Existence: derived from `git worktree list`, never the ledger (REQ-007).
# ---------------------------------------------------------------------------

# Every attribute `git worktree list --porcelain` can emit. Anything else in
# the output means we are not reading what we think we are reading.
_PORCELAIN_PREFIXES = ("worktree ", "HEAD ", "locked ", "prunable ")
_PORCELAIN_FLAG_LINES = ("bare", "detached", "locked", "prunable")


def parse_worktree_list(text: str) -> tuple[WorktreeEntry, ...]:
    """Parse porcelain output into entries; raise on anything unrecognized.

    Empty output is undecidable too, not an honest zero: every repository
    lists at least its main worktree, so blank output means the command did
    not run where we think it did.
    """
    entries: list[WorktreeEntry] = []
    path: Path | None = None
    branch = ""
    for line in text.splitlines():
        if not line.strip():
            if path is not None:
                entries.append(WorktreeEntry(path=path, branch=branch))
            path = None
            branch = ""
        elif line.startswith("worktree "):
            path = Path(line.removeprefix("worktree "))
        elif line.startswith("branch refs/heads/"):
            branch = line.removeprefix("branch refs/heads/")
        elif line.startswith(_PORCELAIN_PREFIXES) or line in _PORCELAIN_FLAG_LINES:
            continue
        else:
            raise WorktreeCapacityError(
                "cannot parse `git worktree list --porcelain` output: "
                f"unrecognized line {line!r}; refusing to guess the "
                "worktree set (fail closed, REQ-007)."
            )
    if path is not None:
        entries.append(WorktreeEntry(path=path, branch=branch))
    if not entries:
        raise WorktreeCapacityError(
            "`git worktree list --porcelain` listed no worktrees; every "
            "repository lists at least its main worktree, so the output is "
            "undecidable (fail closed, REQ-007)."
        )
    return tuple(entries)


def run_git_worktree_list(repo_root: Path) -> str:
    """The default GitRunner: real git, real listing."""
    git_executable = shutil.which("git")
    if git_executable is None:
        raise WorktreeCapacityError(
            "git executable not found in PATH; cannot list worktrees "
            "(fail closed, REQ-007)."
        )
    try:
        result = subprocess.run(
            [
                git_executable,
                "-C",
                repo_root.as_posix(),
                "worktree",
                "list",
                "--porcelain",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        raise WorktreeCapacityError(
            f"`git worktree list` failed in {repo_root.as_posix()}: "
            f"{error.stderr.strip() or error}"
        ) from error
    return result.stdout


# ---------------------------------------------------------------------------
# Counting: agent-owned-root children minus the exemption (REQ-008).
# ---------------------------------------------------------------------------


def count_agent_worktrees(
    entries: tuple[WorktreeEntry, ...],
    *,
    agent_root: Path,
    exempt_paths: tuple[Path, ...] = (),
) -> int:
    """How many listed worktrees count against the GLOBAL on-disk view.

    Only direct children of the agent-owned root (`.agents.worktrees`)
    count -- the same ownership definition the git-write guard enforces --
    and the caller passes the exemption in, so the counting rule cannot
    grow a private opinion about what is exempt (REQ-008's counting note).
    """
    root = resolve_fail_closed(agent_root, description="agent-owned worktree root")
    exempt = {path.resolve() for path in exempt_paths}
    count = 0
    for entry in entries:
        resolved = resolve_fail_closed(entry.path, description="listed worktree path")
        if resolved.parent == root and resolved not in exempt:
            count += 1
    return count


def resolve_fail_closed(path: Path, *, description: str) -> Path:
    """Resolve one capacity-decision input into the module's one error net.

    `Path.resolve()` raises shapes the module contract does not emit -- a
    bare `ValueError` on an embedded NUL, `RuntimeError` on a symlink loop
    (the same enumeration `RESOLUTION_FAILURES` documents) -- and a bare
    `ValueError` slips past every consumer that netted only
    `WorktreeCapacityError`/`OSError`. Converting to `WorktreeCapacityError`
    naming the input keeps the contract true: the CLI maps it to exit 2 and
    the hook denies instead of crashing (fail closed, REQ-007)."""
    try:
        return path.resolve()
    except RESOLUTION_FAILURES as error:
        raise WorktreeCapacityError(
            f"cannot resolve the {description} {path.as_posix()!r}: {error}"
        ) from error


def derive_integration_exemptions(
    entries: tuple[WorktreeEntry, ...], *, records_dir: Path
) -> tuple[Path, ...]:
    """The integration worktrees exempt from the cap, read from run records.

    Only an InProgress record's `Integration worktree:` field exempts, and
    only when it matches a worktree git actually lists. A missing record, an
    unparsable one, a Finished one, or a field naming an unlisted path
    exempts nothing -- the worktree counts (fail safe, EC-004). A field that
    cannot be resolved at all (an embedded NUL, a symlink loop) is
    undecidable, not unlisted, and raises `WorktreeCapacityError` naming it
    (fail closed, REQ-007)."""
    return tuple(integration_exemption_owners(entries, records_dir=records_dir))


def integration_exemption_owners(
    entries: tuple[WorktreeEntry, ...], *, records_dir: Path
) -> dict[Path, str]:
    """Map each listed worktree an InProgress run record names as its
    integration worktree to that record's run branch.

    One walker behind the exemption itself (`derive_integration_exemptions`
    returns this map's keys), exposed so a caller that must NOT act on an
    exempt worktree can name the run that owns it -- the acquire CLI's
    reuse refusal for a lease-less integration worktree whose ledger entry
    was lost to a crash (REQ-008). The fail-safe and fail-closed rules are
    exactly the exemption's: a missing, unparsable, or Finished record, or
    a field naming an unlisted path, owns nothing."""
    if not entries:
        return {}
    main_worktree = resolve_fail_closed(
        entries[0].path, description="listed main worktree path"
    )
    listed = {
        resolve_fail_closed(entry.path, description="listed worktree path")
        for entry in entries
    }
    owners: dict[Path, str] = {}
    for record_path in sorted(records_dir.glob("*.md")):
        try:
            text = record_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        state = parse_plan_run_state(text)
        if (
            state is None
            or state.status != "InProgress"
            or not state.integration_worktree
        ):
            continue
        recorded = Path(state.integration_worktree)
        if not recorded.is_absolute():
            recorded = main_worktree / recorded
        resolved = resolve_fail_closed(
            recorded, description="run record's `Integration worktree:` value"
        )
        if resolved in listed:
            owners.setdefault(resolved, state.branch)
    return owners


@dataclass(frozen=True)
class CapacitySnapshot:
    """One consistent capacity view, shared by the CLI and the hook."""

    max_concurrent: int
    agent_worktree_count: int
    exempt_paths: tuple[Path, ...]
    entries: tuple[WorktreeEntry, ...]

    @property
    def acquire_allowed(self) -> bool:
        """True when the capped count is strictly under N (REQ-008)."""
        return self.agent_worktree_count < self.max_concurrent


def capacity_snapshot(
    repo_root: Path,
    *,
    config_path: Path = CONFIG_PATH,
    records_dir: Path | None = None,
    worktree_lister: GitRunner | None = None,
) -> CapacitySnapshot:
    """Load N, list worktrees, and count the GLOBAL capped set in one pass.

    The single composition the hook backstop (and `status`'s inventory)
    consumes, so its raw-`worktree add` denial can never diverge from the
    disk (REQ-010). The acquire CLI's cap is per-run and layers
    `run_capacity_view` on top of this snapshot -- same entries, same
    exemptions, one counting rule per concern in this one module. Run
    records live in the main working tree only, which `git worktree list`
    reports first; `records_dir` overrides that default for tests."""
    max_concurrent = load_max_concurrent_worktrees(config_path)
    lister = worktree_lister if worktree_lister is not None else run_git_worktree_list
    entries = parse_worktree_list(lister(repo_root))
    records = (
        records_dir if records_dir is not None else entries[0].path / PLAN_RUNS_DIR
    )
    exempt_paths = derive_integration_exemptions(entries, records_dir=records)
    agent_worktree_count = count_agent_worktrees(
        entries,
        agent_root=repo_root / AGENT_WORKTREE_ROOT,
        exempt_paths=exempt_paths,
    )
    return CapacitySnapshot(
        max_concurrent=max_concurrent,
        agent_worktree_count=agent_worktree_count,
        exempt_paths=exempt_paths,
        entries=entries,
    )


@dataclass(frozen=True)
class RunCapacityView:
    """The calling run's slice of a global snapshot: the per-run cap's one
    decision input (REQ-008, revised 2026-09-17).

    `holders` pairs every git-listed agent-root worktree that is neither
    exempt nor lease-less with its lease -- and only when that lease's
    `run_id` is the calling run's. Other runs' worktrees (leased or not)
    and lease-less worktrees count against no run, so they are absent by
    construction rather than filtered by each caller.
    """

    snapshot: CapacitySnapshot
    run_id: str
    holders: tuple[tuple[WorktreeEntry, WorktreeLease], ...]

    def __post_init__(self) -> None:
        # The cap's arithmetic compares this identity for equality, so an
        # empty or padded run_id would unbind it -- refuse at construction,
        # never inside a count the identity feeds (fail closed, REQ-007).
        if not self.run_id or self.run_id != self.run_id.strip():
            raise ValueError(
                f"run_id {self.run_id!r} is not a usable run identity: it must "
                "be non-empty, without leading or trailing whitespace."
            )

    @property
    def run_worktree_count(self) -> int:
        """How many slots the calling run currently holds."""
        return len(self.holders)

    @property
    def acquire_allowed(self) -> bool:
        """True when the run's counted slots are strictly under N."""
        return self.run_worktree_count < self.snapshot.max_concurrent


def run_capacity_view(
    snapshot: CapacitySnapshot,
    *,
    ledger: WorktreeLeaseLedger,
    run_id: str,
    agent_root: Path,
) -> RunCapacityView:
    """Apply the per-run counting rule to one global snapshot.

    Only leases naming a listed agent-root child that is not exempt count,
    and only when they carry the calling run's identity; a lease for an
    unlisted worktree counts nothing (existence comes from `git worktree
    list`, never the ledger -- REQ-007), and a lease naming a path outside
    the agent-owned root is invisible here, never executed upon."""
    root = resolve_fail_closed(agent_root, description="agent-owned worktree root")
    exempt = {path.resolve() for path in snapshot.exempt_paths}
    leases_by_path = {
        resolve_fail_closed(lease.worktree, description="lease worktree path"): lease
        for lease in ledger.leases.values()
    }
    holders: list[tuple[WorktreeEntry, WorktreeLease]] = []
    for entry in snapshot.entries:
        resolved = resolve_fail_closed(entry.path, description="listed worktree path")
        if resolved.parent != root or resolved in exempt:
            continue
        lease = leases_by_path.get(resolved)
        if lease is not None and lease.run_id == run_id:
            holders.append((entry, lease))
    return RunCapacityView(snapshot=snapshot, run_id=run_id, holders=tuple(holders))


# ---------------------------------------------------------------------------
# Durability: clean-or-committed, and a HEAD commit some branch holds,
# before removal AND before re-sync (REQ-013, REQ-109).
# ---------------------------------------------------------------------------

DurabilityAction = Literal["remove", "resync"]


@dataclass(frozen=True)
class DurabilityDecision:
    """Whether one destructive action may proceed, and why not.

    `allowed == (reason == "")` holds by construction: a refusal without its
    reason is unactionable and an allowance with a reason is contradictory,
    so `__post_init__` rejects both instead of letting one reach a caller.
    """

    action: DurabilityAction
    allowed: bool
    reason: str

    def __post_init__(self) -> None:
        if self.allowed != (self.reason == ""):
            raise ValueError(
                f"inconsistent {self.action!r} durability decision: allowed="
                f"{self.allowed} with reason {self.reason!r} -- an allowance "
                "carries an empty reason and a refusal names its reason."
            )


@dataclass(frozen=True)
class HeadProbe:
    """One probe of a worktree's HEAD, both halves of it: the commit HEAD
    names and that probe's verdict on whether any branch holds it.

    The two describe a single inspection of the same HEAD, so the probe
    yields them as one record and `durability_decision` accepts nothing
    else -- a caller cannot pair one probe's commit with another probe's
    reachability verdict, which would name the wrong commit in a REQ-109
    refusal (or excuse the right one). A commit that names nothing -- empty
    or whitespace -- is refused at construction, the same invariant shape
    `DurabilityDecision` enforces on itself: a refusal citing a blank
    commit would point nowhere, so the probe cannot exist as one."""

    commit: str
    branch_reachable: bool

    def __post_init__(self) -> None:
        if not self.commit or self.commit != self.commit.strip():
            raise ValueError(
                f"commit {self.commit!r} is not a usable commit name: it must "
                "be non-empty, without leading or trailing whitespace."
            )


def durability_decision(
    action: DurabilityAction,
    *,
    has_uncommitted_work: bool,
    head_probe: HeadProbe,
) -> DurabilityDecision:
    """Gate the acquire CLI's two destructive call sites on the same
    invariant: `release`'s removal and `_reuse_worktree`'s re-sync of a
    reused worktree to another tip.

    Both paths call this one predicate, so neither can drift into dropping
    uncommitted work (REQ-013): commit to the holder's branch or verify the
    tree clean first. A caller may satisfy a refusal by committing the work
    (commit-then-proceed -- release does exactly that, since a refused tree
    belongs to the calling run itself); what it may never do is run the
    destructive action past a refusal.

    Uncommitted work answers first, so a dirty tree keeps exactly today's
    refusal whatever the reachability. Second (REQ-109): a CLEAN tree whose
    HEAD commit no branch holds is refused too -- `head_probe` carries both
    halves of one probe of that HEAD, the commit and the probe's
    reachability verdict over `refs/heads/*` and `refs/remotes/*` (a tag
    does not hold a commit), so the refusal names the commit that verdict
    actually belongs to. Removing the worktree or re-syncing it to another
    tip would orphan such a commit at the next gc; the refusal names the
    commit and the recovery: branch it, or move the worktree onto a
    branch."""
    if not has_uncommitted_work and not head_probe.branch_reachable:
        return DurabilityDecision(
            action=action,
            allowed=False,
            reason=(
                f"refusing to {action}: HEAD commit {head_probe.commit} is "
                "reachable from no branch (local or remote-tracking; a tag "
                "does not hold it), so removal or re-sync would lose it. "
                "Make the commit reachable first: branch it (`git branch "
                f"<name> {head_probe.commit}`) or move the worktree onto a "
                "branch (`git switch -c <name>`) (REQ-109)."
            ),
        )
    if not has_uncommitted_work:
        return DurabilityDecision(action=action, allowed=True, reason="")
    return DurabilityDecision(
        action=action,
        allowed=False,
        reason=(
            f"refusing to {action}: the worktree has uncommitted work. "
            "Commit it to the holder's branch (or verify the tree clean) "
            "before removal or re-sync to another tip (REQ-013)."
        ),
    )


# ---------------------------------------------------------------------------
# Leases: owning run's identity, holder info, acquire timestamp -- no timer.
# ---------------------------------------------------------------------------


def _require_aware_datetime(value: object, name: str) -> datetime.datetime:
    if not isinstance(value, datetime.datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    return value


@dataclass(frozen=True)
class WorktreeLease:
    """Who holds a worktree, for which run, and since when.

    `run_id` is the acquiring run's branch name: the per-run cap counts only
    leases carrying the calling run's identity, and release frees a slot only
    for the run that owns the lease. There is no timer and no renewal: a live
    holder is never auto-reclaimed, so a stale holder -- a resumed run's
    leftover -- is reclaimed deterministically by that run's own explicit,
    durability-gated `release`.
    """

    worktree: Path
    run_id: str
    holder_pid: int
    holder_host: str
    acquired_at: datetime.datetime

    def __post_init__(self) -> None:
        # The identity is compared for equality across acquire, release, and
        # the per-run count, so a padded or whitespace-only value would be a
        # second, drifting spelling of the run's branch name -- refused at
        # this boundary rather than normalized.
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("run_id must be a non-empty string")
        if self.run_id != self.run_id.strip():
            raise ValueError(
                f"run_id must not have leading or trailing whitespace, got {self.run_id!r}"
            )
        if not isinstance(self.holder_pid, int) or isinstance(self.holder_pid, bool):
            raise ValueError("holder_pid must be an integer")
        if self.holder_pid < 1:
            raise ValueError(f"holder_pid must be >= 1, got {self.holder_pid}")
        if not isinstance(self.holder_host, str) or not self.holder_host:
            raise ValueError("holder_host must be a non-empty string")
        _require_aware_datetime(self.acquired_at, "acquired_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "worktree": self.worktree.as_posix(),
            "run_id": self.run_id,
            "holder_pid": self.holder_pid,
            "holder_host": self.holder_host,
            "acquired_at": self.acquired_at.isoformat(),
        }

    @classmethod
    def from_payload(cls, payload: object) -> WorktreeLease:
        """Validate one decoded lease JSON object (unknown keys forbidden)."""
        if not isinstance(payload, dict):
            raise ValueError("lease must be a JSON object")
        allowed = {
            "worktree",
            "run_id",
            "holder_pid",
            "holder_host",
            "acquired_at",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unknown lease fields: {sorted(unknown)}")
        missing = allowed - set(payload)
        if missing:
            raise ValueError(f"missing lease fields: {sorted(missing)}")
        raw_worktree = payload["worktree"]
        raw_at = payload["acquired_at"]
        if not isinstance(raw_worktree, str) or not raw_worktree:
            raise ValueError("worktree must be a non-empty path string")
        if not isinstance(raw_at, str):
            raise ValueError("acquired_at must be an ISO datetime string")
        return cls(
            worktree=Path(raw_worktree),
            run_id=payload["run_id"],
            holder_pid=payload["holder_pid"],
            holder_host=payload["holder_host"],
            acquired_at=datetime.datetime.fromisoformat(raw_at),
        )


@dataclass(frozen=True)
class WorktreeLeaseLedger:
    """Every lease, keyed by worktree path (resolved posix form, dict keys
    are str).

    Key/path identity is enforced in resolved form: a key that is not its
    lease's `worktree` after `Path.resolve()` fails validation, so a
    hand-edited or hallucinated ledger is unreadable and `load_leases` fails
    closed on it. Consumers all decide on resolved paths, and keys are
    canonical, so one real directory can hold exactly one lease -- a symlink
    alias of an already-leased directory cannot book it under a second
    spelling.
    """

    leases: dict[str, WorktreeLease] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Resolve each lease path once and require the key to equal the
        resolved posix form. Resolving is non-strict: a lease whose worktree
        is already gone resolves to its own lexical path and still validates
        (existence is re-derived from `git worktree list` at every count,
        never from the ledger). An unresolvable path -- a symlink loop, an
        embedded NUL -- is undecidable, not false, so it resolves through
        the module's fail-closed net: the mapped `WorktreeCapacityError`
        (a ValueError) reaches `load_leases`, which converts it to exit 2,
        instead of a bare `RuntimeError` escaping the model boundary."""
        mismatched = [
            key
            for key, lease in self.leases.items()
            if key
            != resolve_fail_closed(
                lease.worktree, description="lease worktree path"
            ).as_posix()
        ]
        if mismatched:
            raise ValueError(
                "every ledger key must equal its lease's worktree path in "
                f"resolved posix form; mismatched keys: {mismatched}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "leases": {key: lease.to_dict() for key, lease in self.leases.items()}
        }

    @classmethod
    def from_payload(cls, payload: object) -> WorktreeLeaseLedger:
        """Validate one decoded ledger JSON object (unknown keys forbidden)."""
        if not isinstance(payload, dict):
            raise ValueError("lease ledger must be a JSON object")
        unknown = set(payload) - {"leases"}
        if unknown:
            raise ValueError(f"unknown lease-ledger fields: {sorted(unknown)}")
        raw_leases = payload.get("leases", {})
        if not isinstance(raw_leases, dict):
            raise ValueError("leases must be a JSON object")
        return cls(
            leases={
                key: WorktreeLease.from_payload(raw)
                for key, raw in raw_leases.items()
            }
        )


def load_leases(path: Path) -> WorktreeLeaseLedger:
    """The ledger on disk, or an empty one when no leases exist yet.

    An existing but unreadable or unparsable ledger raises instead of
    reading as empty: an acquire decision made on a silently emptied ledger
    could double-book worktrees, and plan section 3(c) names "unreadable
    ledger" as exit-2 undecidable input."""
    if not path.is_file():
        return WorktreeLeaseLedger()
    try:
        return WorktreeLeaseLedger.from_payload(
            json.loads(path.read_text(encoding="utf-8"))
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise WorktreeCapacityError(
            f"worktree lease ledger at {path.as_posix()} is unreadable or "
            f"unparsable ({error}); refusing to decide capacity on it "
            "(fail closed)."
        ) from error


def store_leases(path: Path, ledger: WorktreeLeaseLedger) -> None:
    """Persist the whole ledger atomically -- a torn write would wedge every
    later acquire into fail-closed; callers hold the capacity lock around
    read-modify-write so concurrent acquirers cannot lose a lease."""
    write_text_atomic(path, json.dumps(ledger.to_dict()))


# ---------------------------------------------------------------------------
# Lock: kernel-released, spanning count+create (REQ-007, DD-004).
# ---------------------------------------------------------------------------


@contextmanager
def capacity_lock(lock_path: Path) -> Iterator[None]:
    """Exclusive advisory lock held only across the count+create critical
    section.

    The kernel-released claim scoped here is the lock itself: it lives in an
    open file descriptor, so the holder's death releases it and the next
    acquirer proceeds (DD-004) -- a crash cannot wedge acquisition. It does
    NOT make the section's effects atomic: a crash between creating a
    worktree and writing its lease leaves a git-listed, lease-less worktree
    behind. That orphan counts against no run (the cap counts leases) and is
    recovered by the acquire CLI's reuse path -- an available worktree is
    re-synced and leased, never removed. Callers keep the section brief --
    count, create, write the lease, yield."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
