"""Filesystem resolution of which git checkout a location belongs to.

A leaf module: it reads `.git` entries off disk and answers questions about
checkouts. It knows nothing about shell commands, git subcommands, or which
of them are dangerous — `src/utils/git_write_guard.py` layers that policy on
top of these answers.
"""

from __future__ import annotations

from pathlib import Path

# The one directory this repo's agents create worktrees under, relative to the
# main checkout. A worktree is "agent-owned" iff it is a DIRECT child of it.
AGENT_WORKTREE_ROOT = Path(".agents.worktrees")

# The probes below raise more than `OSError` (measured on CPython 3.12.12):
# `resolve()` raises `ValueError` on an embedded NUL and `RuntimeError` on a
# symlink loop, and `read_text()` raises `UnicodeDecodeError` — a `ValueError`
# subclass — on a `.git` pointer that is not UTF-8. Every function here feeds
# a PreToolUse hook, where an uncaught exception is a NON-blocking error the
# tool proceeds past — a fail-open dressed as fail-closed. Each guarded site
# catches exactly this enumerated set (never a blanket catch-all, REQ-013)
# and fails closed toward the narrower tier: None where the contract is
# `Path | None`, False where it is `bool`.
RESOLUTION_FAILURES = (OSError, RuntimeError, ValueError)


def find_git_entry(start: Path) -> Path | None:
    """Return the nearest `.git` file or directory at or above `start`, or
    None when the walk cannot decide. A probe that raises (a directory in the
    walk is unreadable) ends the walk as None: skipping the level that could
    not be inspected would climb past it and hand back a higher checkout's
    entry while a nearer `.git` could hide below the unreadable level."""

    try:
        for directory in (start, *start.parents):
            candidate = directory / ".git"
            if candidate.exists():
                return candidate
    except RESOLUTION_FAILURES:
        return None
    return None


def main_checkout_root(effective_location: Path | None) -> Path | None:
    """Resolve the main checkout root owning `effective_location`. A push's
    per-run state record, and the agent-owned worktree root, both live only in
    the main working tree, so both must resolve back to it from wherever the
    command runs. Returns the directory holding the `.git` directory when the
    location is inside the main checkout (`find_git_entry` walks UP, so a
    subdirectory resolves to its owning checkout, never to itself), the
    referenced main checkout when it is a linked worktree (its `.git` is a file
    whose `gitdir:` line points at `<main>/.git/worktrees/<name>`), or None
    (fail closed) if resolution fails at any step."""

    if effective_location is None:
        return None

    git_entry = find_git_entry(effective_location)
    if git_entry is None:
        return None
    try:
        if git_entry.is_dir():
            return git_entry.parent
        gitdir_line = next(
            line
            for line in git_entry.read_text(encoding="utf-8").splitlines()
            if line.startswith("gitdir:")
        )
    except (*RESOLUTION_FAILURES, StopIteration):
        return None

    gitdir = gitdir_line[len("gitdir:") :].strip().replace("\\", "/")
    marker = "/.git/worktrees/"
    if marker not in gitdir:
        return None

    main_root = gitdir.split(marker, 1)[0]
    return Path(main_root) if main_root else None


def enclosing_checkout_root(location: Path | None) -> Path | None:
    """The working-tree root owning `location`: the directory holding the
    nearest `.git` entry at or above it. Agents run commands from
    subdirectories all the time, so ownership is tested against this root
    rather than the raw location — the same tolerance `cwd_is_linked_worktree`
    already has. Also means a bare `mkdir .agents.worktrees/fake` is not
    agent-owned: the walk finds the main checkout's `.git` and yields the main
    checkout, whose own parent is not the agent root."""

    if location is None:
        return None
    git_entry = find_git_entry(location)
    return None if git_entry is None else git_entry.parent


def is_agent_owned_worktree(location: Path | None, cwd: Path | None) -> bool:
    """True when `location` is a worktree this repo's agents own: a DIRECT
    child of `<main checkout>/.agents.worktrees`. Ownership is decided by path
    alone — branch, contents and git metadata are never consulted.

    The main checkout is always anchored on the session `cwd` (via
    `main_checkout_root`, which follows a linked worktree's `gitdir:` line back
    to the main working tree), never on a `-C`/`--git-dir`/`--work-tree`
    override, so a command cannot aim this test at another repository's
    `.agents.worktrees`.

    `location` is fully resolved while the root is joined onto the resolved
    main checkout LITERALLY, so a symlink at `.agents.worktrees/<name>` — or at
    `.agents.worktrees` itself — resolves out of the literal root and is
    denied. Fails closed (False) when `location` is None or not absolute, when
    the main checkout cannot be resolved, and when resolving raises — an
    embedded NUL (`ValueError`), a symlink loop (`RuntimeError`), or an OS
    error."""

    if location is None or not location.is_absolute():
        return False
    root = main_checkout_root(cwd)
    if root is None:
        return False
    try:
        return location.resolve().parent == root.resolve() / AGENT_WORKTREE_ROOT
    except RESOLUTION_FAILURES:
        return False


def cwd_is_linked_worktree(cwd: Path | None) -> bool:
    """True when `cwd` resolves inside a linked git worktree, not the main
    checkout. A linked worktree's `.git` is a file (not a directory) whose
    `gitdir:` line points at `<repo>/.git/worktrees/<name>` — this walks up
    from `cwd` to find that marker instead of assuming a fixed path
    convention, so it works for any worktree location."""

    if cwd is None:
        return False

    git_entry = find_git_entry(cwd)
    if git_entry is None:
        return False

    try:
        if git_entry.is_dir():
            return False
        gitdir_line = next(
            line
            for line in git_entry.read_text(encoding="utf-8").splitlines()
            if line.startswith("gitdir:")
        )
    except (*RESOLUTION_FAILURES, StopIteration):
        return False

    return "/worktrees/" in gitdir_line.replace("\\", "/")
