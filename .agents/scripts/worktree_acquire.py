"""Mediate every agent-worktree create/reuse/remove decision (REQ-007).

The one script agents use to acquire, inspect, and release worktrees under
`.agents/worktrees/`, enforcing the PER-RUN cap N from `.agents/config.toml`
through the shared `agentic_workflows.worktree_capacity` module (REQ-008, revised
2026-09-17): the cap counts ONLY worktrees leased to the calling run --
identified by the required `--run <branch>` -- while other runs' worktrees,
leased or not, never count and are never touched. The run's single
integration worktree stays exempt, derived from the run-state record.

Contract: `acquire` prints exactly one worktree path on stdout; exit 0
succeeded, 1 was refused (actionable stderr naming your run's slots and
holders, plus the next actions -- land or release one of YOUR holders),
2 hit undecidable input and names it (missing `--run`, unparseable git
output, missing config, unreadable or unpersistable ledger, a new branch
whose run branch does not exist -- REQ-007 fail-closed).

A NEW `--branch` starts at the run's own branch (`--run`), never at the main
checkout's HEAD or at whatever a reused worktree has checked out; an existing
`--branch` is attached to as-is. The run branch must therefore already exist
whenever a new branch is created (run-start Step 0.5 creates it before any
worktree is acquired); otherwise nothing is created and acquire exits 2.

`acquire` NEVER removes a worktree: under the kernel-released
`capacity_lock` (so a crashed holder cannot wedge the next acquirer) it
counts the calling run's leases, refuses at N, else reuses an available
lease-less worktree or creates one, and writes the lease -- nothing else.
The ONLY destructive path is `release --name --run`: it refuses a worktree
leased to another run (or to no run), and on the calling run's own dirty
tree it commits the work to the branch before removing (REQ-013, gated by
the shared `durability_decision` predicate, as is reuse's re-sync); a clean
tree whose HEAD commit no branch holds refuses both destructive paths,
naming the commit and its recovery (REQ-109). There
is no timer and no renewal: a live holder is never auto-reclaimed; a
resumed run reclaims its own stale holders via status -> release -> acquire.
All paths are resolved from the repository root (git's main worktree),
never from the process CWD, so the CLI and the hook find the same config
and records from any directory.
"""

from __future__ import annotations


# --- standalone bootstrap -------------------------------------------------
# This script may run from a consumer repo via symlink; resolve its real
# location and put both the runtime root and the sibling-script directory on
# sys.path before any agentic_workflows/sibling imports run.
def _bootstrap() -> None:
    import sys as _sys
    from pathlib import Path as _Path
    here = _Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "agentic_workflows" / "__init__.py").is_file():
            _sys.path.insert(0, str(candidate))
            break
    if str(here) not in _sys.path:
        _sys.path.insert(0, str(here))


_bootstrap()
# --------------------------------------------------------------------------

import argparse
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from agentic_workflows.git_checkout_resolution import AGENT_WORKTREE_ROOT
from agentic_workflows.plan_run_paths import PLAN_RUNS_DIR
from agentic_workflows.time import utc_now
from agentic_workflows.worktree_capacity import (
    CapacitySnapshot,
    HeadProbe,
    RunCapacityView,
    WorktreeCapacityError,
    WorktreeEntry,
    WorktreeLease,
    WorktreeLeaseLedger,
    capacity_lock,
    capacity_snapshot,
    durability_decision,
    integration_exemption_owners,
    load_leases,
    parse_worktree_list,
    resolve_config_path,
    resolve_fail_closed,
    run_capacity_view,
    run_git_worktree_list,
    store_leases,
)

# The ledger and lock live under the agent-owned worktree root (the spec's
# stated ledger home). They are files, and the cap counts only worktrees git
# actually lists, so they never distort the count (REQ-008).
LEDGER_FILENAME = Path("leases.json")
LOCK_FILENAME = Path("acquire.lock")

_RESERVED_NAMES = frozenset({".", ".."})
_NAME_FORBIDDEN_CHARACTERS = ("/", "\\")

_RELEASE_COMMIT_MESSAGE = (
    "worktree-acquire: commit uncommitted work before releasing the worktree"
)
_REUSE_COMMIT_MESSAGE = (
    "worktree-acquire: commit uncommitted work before re-syncing the worktree"
)
_NEXT_ACTIONS_LINE = (
    "next actions: land or release one of YOUR run's holders "
    "(`release --name <name> --run <branch>`)."
)


@dataclass(frozen=True)
class _CliContext:
    """Repo-anchored paths each subcommand derives once and passes down."""

    repo_root: Path
    agent_root: Path
    config_path: Path
    records_dir: Path
    ledger_path: Path
    lock_path: Path


def _git_toplevel() -> Path:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise WorktreeCapacityError(
            "git executable not found in PATH; cannot resolve the repository "
            "root (fail closed, REQ-007)."
        )
    result = subprocess.run(
        [git_executable, "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise WorktreeCapacityError(
            "cannot resolve the repository root from the current directory: "
            f"{result.stderr.strip() or 'not a git repository'} "
            "(fail closed, REQ-007)."
        )
    return Path(result.stdout.strip())


def _resolve_context() -> _CliContext:
    entries = parse_worktree_list(run_git_worktree_list(_git_toplevel()))
    repo_root = entries[0].path  # git lists the main worktree first
    agent_root = repo_root / AGENT_WORKTREE_ROOT
    return _CliContext(
        repo_root=repo_root,
        agent_root=agent_root,
        config_path=resolve_config_path(repo_root),
        records_dir=repo_root / PLAN_RUNS_DIR,
        ledger_path=agent_root / LEDGER_FILENAME,
        lock_path=agent_root / LOCK_FILENAME,
    )


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise WorktreeCapacityError(
            f"git executable not found in PATH; cannot run `git {args[0]}` "
            "(fail closed, REQ-007)."
        )
    return subprocess.run(
        [git_executable, *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def _validate_name(name: str) -> None:
    """Reject anything that is not one usable path segment, before it can
    become a path operand -- including the lease ledger's own file names,
    which a worktree must never be created at (fail closed, REQ-007)."""
    if (
        not name
        or name in _RESERVED_NAMES
        or name != name.strip()
        or not name.isprintable()
        or any(character in name for character in _NAME_FORBIDDEN_CHARACTERS)
    ):
        raise WorktreeCapacityError(
            f"worktree name {name!r} is not a single usable path segment under "
            f"{AGENT_WORKTREE_ROOT.as_posix()}; refusing to guess the target "
            "path (fail closed, REQ-007)."
        )
    if name in (LEDGER_FILENAME.as_posix(), LOCK_FILENAME.as_posix()):
        raise WorktreeCapacityError(
            f"worktree name {name!r} is reserved for the lease ledger's own "
            f"files under {AGENT_WORKTREE_ROOT.as_posix()} "
            f"({LEDGER_FILENAME.as_posix()}, {LOCK_FILENAME.as_posix()}): a "
            "worktree there would sit at the ledger path and wedge every "
            "later acquire (fail closed, REQ-007)."
        )


def _validate_branch(context: _CliContext, branch: str) -> None:
    """Gate the branch operand through git's own ref-format check before it
    can become `git worktree add -b` input (fail closed, REQ-007)."""
    checked = _git(context.repo_root, "check-ref-format", "--branch", branch)
    if checked.returncode != 0:
        raise WorktreeCapacityError(
            f"branch name {branch!r} was rejected by `git check-ref-format "
            f"--branch` ({checked.stderr.strip() or 'not a valid branch name'}); "
            "refusing to pass it to git (fail closed, REQ-007)."
        )


def _print_path(path: Path) -> None:
    """The CLI's stdout contract: exactly one path, nothing else. `scripts/`
    CLIs print their own contract output; `scripts/sdd_workspace.py` is the
    precedent and documents the T201-exemption rationale."""
    print(path.as_posix())  # noqa: T201


def _format_run_picture(view: RunCapacityView) -> str:
    """The run-scoped slots/holders picture shared by the cap-full refusal
    and `status --run`, so the two surfaces cannot diverge (F-02). Only the
    calling run's holders appear: other runs' worktrees never count and are
    never this run's to act on."""
    free = max(0, view.snapshot.max_concurrent - view.run_worktree_count)
    lines = [
        f"your run {view.run_id}: {view.run_worktree_count} of "
        f"{view.snapshot.max_concurrent} slots in use, {free} free.",
        "your run's worktrees:",
    ]
    for entry, lease in view.holders:
        lines.append(
            f"  {entry.path.resolve().as_posix()} "
            f"branch={entry.branch or 'detached'}: "
            f"pid={lease.holder_pid} host={lease.holder_host} "
            f"acquired={lease.acquired_at.isoformat()}"
        )
    lines.append(_NEXT_ACTIONS_LINE)
    return "\n".join(lines) + "\n"


def _format_inventory(
    snapshot: CapacitySnapshot, ledger: WorktreeLeaseLedger, *, agent_root: Path
) -> str:
    """The global worktree inventory `status` prints without `--run`: every
    agent-root worktree git lists, with its holder and owning run. Read-only
    context for the per-run cap -- no verdict, since the cap counts one
    run's leases, not this disk."""
    lines = [
        "agent worktrees (the cap N is per run; name your run with "
        "`status --run <branch>` for its slots):",
    ]
    root = agent_root.resolve()
    exempt = {path.resolve() for path in snapshot.exempt_paths}
    leases_by_path = {
        lease.worktree.resolve(): lease for lease in ledger.leases.values()
    }
    for entry in snapshot.entries:
        resolved = entry.path.resolve()
        if resolved.parent != root or resolved in exempt:
            continue
        lease = leases_by_path.get(resolved)
        if lease is None:
            holder = "no lease on record"
        else:
            holder = (
                f"run={lease.run_id} pid={lease.holder_pid} "
                f"host={lease.holder_host} "
                f"acquired={lease.acquired_at.isoformat()}"
            )
        lines.append(
            f"  {resolved.as_posix()} branch={entry.branch or 'detached'}: {holder}"
        )
    return "\n".join(lines) + "\n"


def _remove_worktree(context: _CliContext, worktree: Path) -> str | None:
    """The bare `git worktree remove`, without --force: git re-verifies the
    tree is clean at removal time. Returns None on success or a failure
    note naming what went wrong."""
    removal = _git(context.repo_root, "worktree", "remove", worktree.as_posix())
    if removal.returncode != 0:
        return (
            f"`git worktree remove {worktree.as_posix()}` failed: "
            f"{removal.stderr.strip()}"
        )
    return None


def _detached_head_note(worktree: Path) -> str | None:
    """The durability commit's precondition: HEAD must name a branch. On a
    detached HEAD the commit would land on no branch and become unreachable
    at the next gc, so the caller must fail closed instead of satisfying the
    durability refusal by committing."""
    current = _git(worktree, "rev-parse", "--abbrev-ref", "HEAD")
    if current.returncode != 0:
        return f"cannot inspect {worktree.as_posix()}: {current.stderr.strip()}"
    if current.stdout.strip() == "HEAD":
        return (
            f"{worktree.as_posix()} is on a detached HEAD; commit would "
            "orphan the work -- attach the worktree to a branch first"
        )
    return None


def _branch_reachable_head(worktree: Path) -> HeadProbe | str:
    """One probe of HEAD -- commit and branch-reachability verdict together,
    the record `durability_decision` consumes -- or the note naming why git
    could not tell (the caller refuses a worktree it cannot inspect).

    Reachability is defined over branch refs only -- `refs/heads/*` and
    `refs/remotes/*`; tags do not hold a commit (REQ-109).
    `rev-list --count <commit> --not --branches --remotes` is 0 exactly when
    some branch contains the commit; one probe yields the record whole, so
    the commit named in a refusal and its verdict cannot drift apart."""
    head = _git(worktree, "rev-parse", "HEAD")
    if head.returncode != 0:
        return head.stderr.strip()
    commit = head.stdout.strip()
    contained = _git(
        worktree, "rev-list", "--count", commit, "--not", "--branches", "--remotes"
    )
    if contained.returncode != 0:
        return contained.stderr.strip()
    branch_reachable = contained.stdout.strip() == "0"
    return HeadProbe(commit=commit, branch_reachable=branch_reachable)


def _commit_uncommitted_work(worktree: Path, message: str) -> str | None:
    """Stage and commit the worktree's uncommitted work to its own branch.
    Returns None on success or a failure note naming what went wrong."""
    staged = _git(worktree, "add", "-A")
    if staged.returncode != 0:
        return (
            f"cannot stage uncommitted work in {worktree.as_posix()}: "
            f"{staged.stderr.strip()}"
        )
    committed = _git(worktree, "commit", "-m", message)
    if committed.returncode != 0:
        return (
            f"cannot commit uncommitted work in {worktree.as_posix()}: "
            f"{committed.stderr.strip()}"
        )
    return None


def _local_branch_ref(branch: str) -> str:
    return f"refs/heads/{branch}"


def _branch_exists(context: _CliContext, branch: str) -> bool:
    found = _git(
        context.repo_root, "rev-parse", "--verify", "--quiet", _local_branch_ref(branch)
    )
    return found.returncode == 0


def _branch_operands(
    context: _CliContext, branch: str, run_branch: str
) -> tuple[str, ...]:
    """The trailing operands `git worktree add <path>` and `git checkout`
    share. An existing branch is attached to as-is: the documented recovery
    path re-creates a worktree from a group's retained branch (REQ-017), the
    run's integration worktree attaches to the run branch run-start Step 0.5
    already created, and `-b` fails on an existing branch -- acquire must
    never be unable to re-attach. A NEW branch starts at the run's own branch
    (run-start Step 1 item 1), never at the main checkout's HEAD or at
    whatever a reused worktree has checked out. The start point is the fully
    qualified `refs/heads/<run-branch>` -- the very ref verified to exist -- so
    a same-named tag can never be resolved in its place. With no run branch
    there is no start point, and falling back to HEAD is the defect: fail
    closed (REQ-007)."""
    if _branch_exists(context, branch):
        return (branch,)
    if not _branch_exists(context, run_branch):
        raise WorktreeCapacityError(
            f"new branch {branch!r} must start at its run's branch, but run "
            f"branch {run_branch!r} does not exist; create the run branch "
            "first (run-start Step 0.5 creates it before any worktree is "
            "acquired), or correct --run (fail closed, REQ-007)."
        )
    return ("-b", branch, _local_branch_ref(run_branch))


def _create_worktree(
    context: _CliContext, target: Path, branch: str, run_branch: str
) -> str | None:
    """Create the worktree in the guard-approved fully-substituted shape:
    `git -C <main-checkout> worktree add <main-checkout>/.agents/worktrees/
    <name> -b <branch> refs/heads/<run-branch>` for a new branch, or
    `... <name> <branch>` when the branch already exists (see
    `_branch_operands`)."""
    operands = _branch_operands(context, branch, run_branch)
    result = _git(context.repo_root, "worktree", "add", target.as_posix(), *operands)
    if result.returncode != 0:
        return (
            f"`git worktree add {target.as_posix()} {' '.join(operands)}` failed: "
            f"{result.stderr.strip()}"
        )
    return None


def _reuse_worktree(
    context: _CliContext, entry: WorktreeEntry, branch: str, run_branch: str
) -> str | None:
    """Bring an available (lease-less) worktree to the requested branch:
    `checkout <branch>` for an existing one, else `checkout -b <branch>
    refs/heads/<run-branch>` -- a new branch starts at the run's own branch,
    never at the previous group's tip this worktree still has checked out (see
    `_branch_operands`, decided FIRST so a missing run branch refuses before
    anything is committed or moved). Re-sync is destructive reuse, so the
    shared durability predicate gates it (REQ-013): its refusal is satisfied
    by committing the uncommitted work to the worktree's own branch before
    proceeding, never dropped -- unless HEAD is detached, where the commit
    would orphan the work and the refusal stands (fail closed). The same
    predicate refuses a CLEAN worktree whose HEAD commit no branch holds
    (REQ-109): re-syncing it to another tip would orphan the commit, so the
    refusal names it and the recovery instead. A HEAD git cannot report is
    refused as a worktree that could not be inspected, never read as some
    other branch to check out over."""
    worktree = entry.path
    operands = _branch_operands(context, branch, run_branch)
    status = _git(worktree, "status", "--porcelain")
    if status.returncode != 0:
        return f"cannot inspect {worktree.as_posix()}: {status.stderr.strip()}"
    probed = _branch_reachable_head(worktree)
    if isinstance(probed, str):
        return f"cannot inspect {worktree.as_posix()}: {probed}"
    decision = durability_decision(
        "resync",
        has_uncommitted_work=bool(status.stdout.strip()),
        head_probe=probed,
    )
    if not decision.allowed:
        if not bool(status.stdout.strip()):
            # Clean but branch-less HEAD: the commit is the work, and the
            # re-sync would orphan it -- no commit-then-proceed exists here.
            return f"cannot reuse {worktree.as_posix()}: {decision.reason}"
        detached = _detached_head_note(worktree)
        if detached is not None:
            return f"cannot reuse {worktree.as_posix()}: {decision.reason} {detached}"
        committed = _commit_uncommitted_work(worktree, _REUSE_COMMIT_MESSAGE)
        if committed is not None:
            return f"cannot reuse {worktree.as_posix()}: {decision.reason} {committed}"
    current = _git(worktree, "rev-parse", "--abbrev-ref", "HEAD")
    if current.returncode != 0:
        return f"cannot inspect {worktree.as_posix()}: {current.stderr.strip()}"
    if current.stdout.strip() == branch:
        return None
    switched = _git(worktree, "checkout", *operands)
    if switched.returncode != 0:
        return (
            f"cannot re-sync {worktree.as_posix()} to {branch}: "
            f"{switched.stderr.strip()}"
        )
    return None


def _acquire_locked(context: _CliContext, args: argparse.Namespace) -> tuple[int, Path]:
    """The count-decide-create critical section, already under the lock.
    Returns (exit code, target path)."""
    target = context.agent_root / args.name
    resolved_target = resolve_fail_closed(target, description="--name worktree path")
    ledger = load_leases(context.ledger_path)
    snapshot = capacity_snapshot(
        context.repo_root,
        config_path=context.config_path,
        records_dir=context.records_dir,
    )
    view = run_capacity_view(
        snapshot,
        ledger=ledger,
        run_id=args.run,
        agent_root=context.agent_root,
    )
    if not view.acquire_allowed:
        sys.stderr.write(
            f"worktree acquire refused: your run's "
            f"{view.snapshot.max_concurrent} slots are in use.\n"
        )
        sys.stderr.write(_format_run_picture(view))
        return 1, target

    leases_by_path = {
        resolve_fail_closed(holder.worktree, description="lease worktree path"): holder
        for holder in ledger.leases.values()
    }
    listed = {
        resolve_fail_closed(entry.path, description="listed worktree path"): entry
        for entry in snapshot.entries
    }
    existing = listed.get(resolved_target)
    if existing is not None:
        lease = leases_by_path.get(resolved_target)
        if lease is not None:
            # Leases are exclusive -- across runs and within one: a leased
            # worktree is never reused, and another run's worktree is never
            # this run's to touch (REQ-008).
            if lease.run_id != args.run:
                sys.stderr.write(
                    f"worktree acquire refused: {target.as_posix()} is held "
                    f"by run {lease.run_id}; your run ({args.run}) never "
                    "touches another run's worktree.\n"
                    "next actions: choose another name, or work within your "
                    "own run's slots.\n"
                )
            else:
                sys.stderr.write(
                    f"worktree acquire refused: {target.as_posix()} is "
                    "already held by your run; leases are exclusive.\n"
                    "next actions: release it first (`release --name "
                    f"{args.name} --run {args.run}`), or choose another "
                    "name.\n"
                )
            return 1, target
        owner = integration_exemption_owners(
            snapshot.entries, records_dir=context.records_dir
        ).get(resolved_target)
        if owner is not None:
            # The exemption derives from the owning run's own InProgress
            # record, so a lease-less integration worktree is still that
            # run's: re-syncing and re-leasing it here would deadlock the
            # owning run's cap (REQ-008).
            sys.stderr.write(
                f"worktree acquire refused: {target.as_posix()} is the "
                f"integration worktree of run {owner} (its run record names "
                "it; no lease is on record), and your run never touches "
                "another run's worktree.\n"
                "next actions: choose another name, or work within your "
                "own run's slots.\n"
            )
            return 1, target
        error = _reuse_worktree(context, existing, args.branch, args.run)
    else:
        error = _create_worktree(context, target, args.branch, args.run)
    if error is not None:
        sys.stderr.write(f"worktree acquire refused: {error}\n")
        return 1, target

    store_leases(
        context.ledger_path,
        WorktreeLeaseLedger(
            leases={
                **ledger.leases,
                resolved_target.as_posix(): WorktreeLease(
                    worktree=resolved_target,
                    run_id=args.run,
                    holder_pid=os.getpid(),
                    holder_host=platform.node(),
                    acquired_at=utc_now(),
                ),
            }
        ),
    )
    return 0, target


def _cmd_acquire(args: argparse.Namespace) -> int:
    _validate_name(args.name)
    context = _resolve_context()
    _validate_branch(context, args.branch)
    # The run identity is validated with the same git gate, BEFORE the lock
    # and any side effect: an empty or whitespace-only --run would unbind
    # the per-run cap and fail lease validation only after the worktree had
    # been created or reused -- stranding a worktree no release could free
    # (fail closed at the boundary, REQ-007).
    _validate_branch(context, args.run)
    with capacity_lock(context.lock_path):
        exit_code, target = _acquire_locked(context, args)
    if exit_code == 0:
        _print_path(target)
    return exit_code


def _cmd_status(args: argparse.Namespace) -> int:
    context = _resolve_context()
    ledger = load_leases(context.ledger_path)
    snapshot = capacity_snapshot(
        context.repo_root,
        config_path=context.config_path,
        records_dir=context.records_dir,
    )
    if args.run is None:
        # No run named: the global read-only inventory -- on-disk context for
        # the one-time residue hygiene disposition (REQ-012), not any gate's
        # predicate. The cap counts one run's leases, so a verdict without a
        # run would be a guess; name the run for the per-run picture.
        sys.stdout.write(
            _format_inventory(snapshot, ledger, agent_root=context.agent_root)
        )
        return 0
    _validate_branch(context, args.run)
    view = run_capacity_view(
        snapshot,
        ledger=ledger,
        run_id=args.run,
        agent_root=context.agent_root,
    )
    sys.stdout.write(_format_run_picture(view))
    return 0


def _cmd_release(args: argparse.Namespace) -> int:
    _validate_name(args.name)
    context = _resolve_context()
    _validate_branch(context, args.run)
    with capacity_lock(context.lock_path):
        entries = parse_worktree_list(run_git_worktree_list(context.repo_root))
        target = context.agent_root / args.name
        resolved_target = resolve_fail_closed(
            target, description="--name worktree path"
        )
        listed_paths = {
            resolve_fail_closed(entry.path, description="listed worktree path")
            for entry in entries
        }
        if resolved_target not in listed_paths:
            sys.stderr.write(
                f"worktree release refused: no worktree at {target.as_posix()} "
                "in `git worktree list`; nothing to release.\n"
            )
            return 1
        ledger = load_leases(context.ledger_path)
        leases_by_path = {
            resolve_fail_closed(
                holder.worktree, description="lease worktree path"
            ): holder
            for holder in ledger.leases.values()
        }
        lease = leases_by_path.get(resolved_target)
        if lease is None:
            sys.stderr.write(
                f"worktree release refused: no lease on record for "
                f"{target.as_posix()}; only a worktree your run leased can "
                "be released.\n"
            )
            return 1
        if lease.run_id != args.run:
            # A slot is freed only by the run that owns the lease: another
            # run's worktree is never this run's to remove (REQ-008).
            sys.stderr.write(
                f"worktree release refused: {target.as_posix()} is held by "
                f"run {lease.run_id}; your run ({args.run}) never touches "
                "another run's worktree.\n"
            )
            return 1
        status = _git(target, "status", "--porcelain")
        if status.returncode != 0:
            sys.stderr.write(
                f"worktree release refused: cannot inspect {target.as_posix()}: "
                f"{status.stderr.strip()}\n"
            )
            return 1
        probed = _branch_reachable_head(target)
        if isinstance(probed, str):
            sys.stderr.write(
                f"worktree release refused: cannot inspect {target.as_posix()}: "
                f"{probed}\n"
            )
            return 1
        decision = durability_decision(
            "remove",
            has_uncommitted_work=bool(status.stdout.strip()),
            head_probe=probed,
        )
        if not decision.allowed:
            if not bool(status.stdout.strip()):
                # Clean but branch-less HEAD: the commit is the work, and the
                # removal would discard it -- no commit-then-proceed exists
                # here (REQ-109).
                sys.stderr.write(
                    f"worktree release refused: {target.as_posix()}: "
                    f"{decision.reason}\n"
                )
                return 1
            # The shared predicate refused the bare removal; commit-then-
            # proceed is the one legal way past it: the dirty work belongs
            # to the calling run itself, so it is committed to the holder's
            # branch first, never discarded (REQ-013). A detached HEAD fails
            # closed instead: committing there would land the work on no
            # branch, unreachable at the next gc.
            detached = _detached_head_note(target)
            if detached is not None:
                sys.stderr.write(
                    f"worktree release refused: {target.as_posix()}: "
                    f"{decision.reason} {detached}\n"
                )
                return 1
            committed = _commit_uncommitted_work(target, _RELEASE_COMMIT_MESSAGE)
            if committed is not None:
                sys.stderr.write(
                    f"worktree release refused: {target.as_posix()}: "
                    f"{decision.reason} {committed}\n"
                )
                return 1
        # Drop the lease BEFORE removal: a persist failure after the removal
        # would strand a lease `release` can never free (its worktree is
        # gone), while this order leaves only the recoverable state the
        # reuse path exists for -- a lease-less worktree (REQ-007).
        store_leases(
            context.ledger_path,
            WorktreeLeaseLedger(
                leases={
                    key: holder
                    for key, holder in ledger.leases.items()
                    if key != resolved_target.as_posix()
                }
            ),
        )
        note = _remove_worktree(context, target)
        if note is not None:
            sys.stderr.write(f"worktree release refused: {target.as_posix()}: {note}\n")
            return 1
    _print_path(target)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="worktree_acquire",
        description=(
            "Mediate agent-worktree creation, inspection, and removal against "
            "the per-run cap N. acquire prints the worktree path on stdout; "
            "exit 0 succeeded, 1 was refused (actionable stderr), 2 hit "
            "undecidable input."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    acquire_parser = subparsers.add_parser(
        "acquire", help="Take a worktree slot for your run (reuse or create)."
    )
    acquire_parser.add_argument(
        "--name",
        required=True,
        help="Worktree directory name under .agents/worktrees/.",
    )
    acquire_parser.add_argument(
        "--branch",
        required=True,
        help="Branch for the worktree: attached to when it exists, else "
        "created at the run's branch (--run).",
    )
    acquire_parser.add_argument(
        "--run",
        required=True,
        help="The acquiring run's branch name: the cap counts your run's "
        "leases only, the lease records this identity, and a new --branch "
        "starts here (this branch must already exist).",
    )
    status_parser = subparsers.add_parser(
        "status",
        help="Print the worktree picture (with --run: your run's slots).",
    )
    status_parser.add_argument(
        "--run",
        required=False,
        help="Your run's branch name; prints your run's slots and holders.",
    )
    release_parser = subparsers.add_parser(
        "release",
        help="Remove your run's worktree (durability-gated) and drop its lease.",
    )
    release_parser.add_argument(
        "--name",
        required=True,
        help="Worktree directory name under .agents/worktrees/.",
    )
    release_parser.add_argument(
        "--run",
        required=True,
        help="The calling run's branch name; only your run's leases can be released.",
    )
    args = parser.parse_args(argv)

    try:
        if args.command == "acquire":
            return _cmd_acquire(args)
        if args.command == "status":
            return _cmd_status(args)
        return _cmd_release(args)
    except WorktreeCapacityError as error:
        sys.stderr.write(
            f"worktree {args.command} failed on undecidable input, failing "
            f"closed: {error}\n"
        )
        return 2
    except OSError as error:
        # The lease ledger and the lock file are the decision's persisted
        # state: a write or lock failure there (a read-only agent root, a
        # full disk) is undecidable input too -- never a traceback, and in
        # release never a removal whose lease could not be dropped.
        sys.stderr.write(
            f"worktree {args.command} could not persist the lease ledger or "
            f"lock file, failing closed: {error}\n"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
