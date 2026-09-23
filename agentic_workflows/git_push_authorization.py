"""Authorization for the one `git push` shape this workflow can ever run.

Extracted from `git_write_guard` when that module crossed the repo's file
line limit: this is the whole push chain and nothing else, and it reaches no
part of the guard's own subcommand policy. It takes the effective checkout
location as an argument rather than resolving it from a token stream, so the
guard stays the single place that reads `-C`/`--git-dir`/`--work-tree`.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from agentic_workflows.git_checkout_resolution import main_checkout_root
from agentic_workflows.plan_run_state import (
    PlanRunState,
    parse_plan_run_state,
    record_path_for_branch,
)

# The protected default branch a push may never target.
DEFAULT_BRANCH = "main"

# Exact token count of the only legitimate push form,
# `git push -u origin HEAD:<branch>` -> ["-u", "origin", "HEAD:<branch>"].
_CANONICAL_PUSH_ARG_COUNT = 3

# A bare trailing output-redirect operator (`>`, `>>`, `1>`, `2>`, `2>>`, ...);
# the shell consumes it (for `2>&1`, splitting `&1` into its own segment)
# before git ever sees argv, so a push's recognized shape cannot depend on it.
_TRAILING_REDIRECT_OPERATOR = re.compile(r"^\d*>{1,2}$")


def _parse_canonical_push_branch(args: list[str]) -> str | None:
    """Return `<branch>` only for the single legitimate push shape,
    `git push -u origin HEAD:<branch>` (exactly `["-u", "origin",
    "HEAD:<non-empty>"]`). None for everything else: this one length/shape
    check categorically rejects bare push, a missing `-u`, `--all`/`--mirror`,
    delete refspecs (`origin :<branch>`), non-`HEAD` sources (`origin
    feature:branch`), and any force flag — each either lengthens the list past
    three tokens or displaces one of the three fixed positions."""

    core, tail = args[:_CANONICAL_PUSH_ARG_COUNT], args[_CANONICAL_PUSH_ARG_COUNT:]
    if len(core) != _CANONICAL_PUSH_ARG_COUNT or core[0] != "-u" or core[1] != "origin":
        return None
    if tail and not all(_TRAILING_REDIRECT_OPERATOR.match(token) for token in tail):
        return None

    prefix = "HEAD:"
    if not core[2].startswith(prefix):
        return None

    branch = core[2][len(prefix) :]
    return branch or None


def _resolve_pushed_head_sha(
    location: Path,
    rev_parse_head: Callable[[Path], str | None] | None,
) -> str | None:
    """Resolve the commit `HEAD` points at in `location` — the commit a push
    would send. `location` is the effective checkout the invocation operates
    against (a `-C`/`--git-dir`/`--work-tree` override when present, else the
    session cwd), never the raw cwd blindly, so `git -C <dir> push` resolves
    `<dir>`'s HEAD — the commit git would actually send. `rev_parse_head` is
    the injected seam; when None the real `git rev-parse HEAD` subprocess runs.
    Fails closed (None) on missing git, OS error, timeout, non-zero exit."""

    if rev_parse_head is not None:
        return rev_parse_head(location)

    git_executable = shutil.which("git")
    if git_executable is None:
        return None

    try:
        result = subprocess.run(
            [git_executable, "rev-parse", "HEAD"],
            cwd=location,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    if result.returncode != 0:
        return None

    return result.stdout.strip()


def _recorded_commit_established(
    location: Path,
    sha: str,
    sha_resolves: Callable[[Path, str], bool] | None,
) -> bool:
    """True when a RECORDED record SHA is established: it names a commit that
    exists in the repository at `location` (REQ-027). Fail-closed posture over
    a fact the record merely asserts — a stale or forged SHA must deny for its
    own reason, not masquerade as an ordinary mismatch. A value starting with
    `-` can never be an object id and is refused before ANY resolution
    attempt — an injected `sha_resolves` included — so it never reaches git's
    argv. Otherwise `sha_resolves` is the injected test seam; when None the
    real `git cat-file -e <sha>^{commit}` subprocess runs. Fails closed
    (False) on missing git, OS error, timeout, or non-zero exit — never raises."""

    if sha.startswith("-"):
        return False

    if sha_resolves is not None:
        return sha_resolves(location, sha)

    git_executable = shutil.which("git")
    if git_executable is None:
        return False

    try:
        result = subprocess.run(
            [git_executable, "cat-file", "-e", f"{sha}^{{commit}}"],
            cwd=location,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    return result.returncode == 0


def _record_establishment_reason(
    record: PlanRunState,
    location: Path,
    sha_resolves: Callable[[Path, str], bool] | None,
) -> str:
    """Denial reason for the first RECORDED fact that fails to establish, or
    "" when they all stand: both SHA fields carry a value naming a commit that
    exists at `location` (REQ-027). Each failing fact names its own fact."""

    if not record.verify_status_sha:
        return "push denied: this round's record carries no verify-status SHA"
    if not record.secret_scan_clean_sha:
        return "push denied: this round's record carries no secret-scan-clean SHA"

    if not _recorded_commit_established(
        location, record.verify_status_sha, sha_resolves
    ):
        return (
            "push denied: this round's verify-status SHA does not resolve to "
            "a commit in this repository"
        )
    if not _recorded_commit_established(
        location, record.secret_scan_clean_sha, sha_resolves
    ):
        return (
            "push denied: this round's secret-scan-clean SHA does not resolve "
            "to a commit in this repository"
        )

    return ""


def _read_branch_record(
    record_path: Path,
    branch: str,
) -> tuple[PlanRunState | None, str]:
    """The plan-run record for `branch`, or `(None, reason)` when one of its
    read-time facts fails: a missing file, an unreadable one (any other
    OSError or a ValueError such as an embedded null byte, named by class),
    non-UTF-8 bytes, an unparseable body, or a record naming a different
    branch. Each failing fact names itself — none borrows another's reason."""

    try:
        record_text = record_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, "push denied: branch not recorded as owned by an active run"
    except UnicodeDecodeError:
        return None, (
            "push denied: the plan-run record for this branch is not valid UTF-8 text"
        )
    except (OSError, ValueError) as read_error:
        return None, (
            "push denied: the plan-run record for this branch could not be read "
            f"({type(read_error).__name__})"
        )
    record = parse_plan_run_state(record_text)
    if record is None:
        return None, (
            "push denied: the plan-run record for this branch exists but "
            "could not be parsed"
        )
    if record.branch != branch:
        return None, (
            "push denied: the plan-run record for this branch names a different branch"
        )
    return record, ""


def push_denial_reason(
    args: list[str],
    effective_location: Path | None,
    rev_parse_head: Callable[[Path], str | None] | None,
    sha_resolves: Callable[[Path, str], bool] | None,
) -> str:
    """Authorization chain for `git push`. Returns "" only when the push is the
    canonical form for a non-default branch that a plan run STILL RUNNING owns,
    whose record could be fully established — every field present, both
    recorded SHAs resolving to real commits in the repository — and both
    recorded SHAs equal the commit actually being pushed. Otherwise a specific,
    non-generic reason names THE fact that failed (INV-1): a missing record, an
    unreadable or unparseable one, a branch mismatch, a run already finished,
    an empty SHA field, a SHA that resolves to no object, and an ordinary
    mismatch each deny with their own message. Fails closed at every step where
    a required fact cannot be established."""

    branch = _parse_canonical_push_branch(args)
    if branch is None:
        return (
            "push denied: not the canonical push form "
            "(git push -u origin HEAD:<branch>)"
        )
    if branch == DEFAULT_BRANCH:
        return "push denied: cannot push to main"

    # `effective_location` is resolved ONCE by the caller and serves both the
    # record lookup and the pushed-commit SHA: `git -C <dir> push` (and
    # --git-dir/--work-tree) makes git operate against <dir>, so the commit it
    # would actually push is <dir>'s HEAD — verifying raw cwd would authorize
    # the wrong location, the bypass class `_commit_is_from_linked_worktree`
    # closes.
    main_root = main_checkout_root(effective_location)
    if main_root is None:
        return "push denied: could not resolve main checkout location"

    record_path = main_root / record_path_for_branch(branch)
    record, read_reason = _read_branch_record(record_path, branch)
    if record is None:
        return read_reason

    # A run's record outlives the run: closing a run leaves the branch and
    # both SHAs standing, so every other fact below still holds and the gate
    # would authorize the push on a record its owner has already closed. What
    # may land after a run is closed is the run owner's decision.
    if record.status != "InProgress":
        return (
            "push denied: this branch's plan run is finished, so its record "
            "no longer authorizes a push"
        )

    if effective_location is None:
        return "push denied: could not resolve the commit being pushed"

    establishment = _record_establishment_reason(
        record, effective_location, sha_resolves
    )
    if establishment:
        return establishment

    pushed_sha = _resolve_pushed_head_sha(effective_location, rev_parse_head)
    if pushed_sha is None:
        return "push denied: could not resolve the commit being pushed"

    if pushed_sha != record.verify_status_sha:
        return (
            "push denied: pushed commit does not match this round's verify-status SHA"
        )
    if pushed_sha != record.secret_scan_clean_sha:
        return (
            "push denied: pushed commit does not match this round's "
            "secret-scan-clean SHA"
        )

    return ""
