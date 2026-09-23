"""Block bare `grep`/`egrep`/`fgrep` searches; require `rg` (ripgrep) instead.

`grep` used to filter another command's piped output (e.g. `ps aux | grep
node`) is unrelated to code/file search and stays allowed — only an
invocation that is a pipeline's own first stage (i.e. it is doing the
searching, not filtering someone else's output) is blocked.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from agentic_workflows.shell_command_parsing import (
    is_control_token,
    strip_shell_wrappers,
    tokenize,
)

GREP_COMMANDS = frozenset({"grep", "egrep", "fgrep"})
PIPE_TOKENS = frozenset({"|"})


def find_bare_grep_segment(command: str) -> str | None:
    """Return the first shell segment that invokes grep/egrep/fgrep as a
    pipeline's first stage, or None if no such segment exists."""

    try:
        tokens = tokenize(command)
    except ValueError:
        return None

    stage_index = 0
    current: list[str] = []

    for token in tokens:
        if token in PIPE_TOKENS:
            blocked = _blocked_segment(current, stage_index)
            if blocked is not None:
                return blocked
            current = []
            stage_index += 1
            continue
        if is_control_token(token):
            blocked = _blocked_segment(current, stage_index)
            if blocked is not None:
                return blocked
            current = []
            stage_index = 0
            continue
        current.append(token)

    return _blocked_segment(current, stage_index)


def _head_is_grep(command_tokens: list[str]) -> bool:
    """True when the head command is grep/egrep/fgrep, however spelled: matched
    on its basename, because `/usr/bin/grep` is the same binary as `grep`. The
    unqualified comparison this replaces let every qualified spelling through
    (measured: `/usr/bin/grep foo src/` was ALLOWED while `grep foo src/` was
    BLOCKED) — the same bypass `git_write_guard._head_is_git` already closes."""
    return (
        bool(command_tokens) and PurePosixPath(command_tokens[0]).name in GREP_COMMANDS
    )


def _blocked_segment(tokens: list[str], stage_index: int) -> str | None:
    if stage_index != 0 or not tokens:
        return None
    if not _head_is_grep(strip_shell_wrappers(tokens)):
        return None
    return " ".join(tokens)


def build_grep_block_message(command: str) -> str | None:
    """Return a user-facing block reason for a bare grep search, or None."""

    blocked_segment = find_bare_grep_segment(command)
    if blocked_segment is None:
        return None

    return (
        "Blocked bare grep search. This project requires `rg` (ripgrep) for "
        "searching code and files (see AGENTS.md section 2). `grep` piped "
        "after another command to filter its output (e.g. `ps aux | grep foo`) "
        f"is still allowed. Blocked segment: {blocked_segment}"
    )
