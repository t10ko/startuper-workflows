"""Block a shell command that would dump more file content into an agent's
context than a bounded budget allows.

Measured cause (2026-09-07, 1,060 subagent runs): shell file-peeking returned
89.6M characters, 60% of everything commands put into agent context, and 76% of
the fat tail of that volume. Every character stays resident and is re-read on
each of that agent's later turns, so a single wide peek is paid many times over.

Scope, stated so a green run is not read as wider assurance than it is:

- Only a peek whose output actually reaches the agent is considered — a stage
  feeding a pipe, or a command writing to a file, is exempt because its output
  is filtered or lands on disk.
- Only the requested line count is judged, and only when it can be measured
  from the command plus the file on disk. A glob, a variable, a missing file,
  or an unparseable command is allowed through: this is a cost guard, not a
  security boundary, and a false block costs a wasted turn.
- Content the agent reads through the harness's own file-reading tool is not
  visible here at all.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from agentic_workflows.plan_run_paths import RUNS_DIR
from agentic_workflows.shell_command_parsing import (
    is_control_token,
    strip_shell_wrappers,
    tokenize,
)

MAX_UNFILTERED_LINES = 120
"""Lines one command may put into an agent's context in one unfiltered read.

A resource budget, not a claim about what any file *is*: it is set at the
measured boundary of the fat tail (results over ~5,000 characters, which carried
50% of all command output while being 12% of calls). Unverified for repositories
with different line lengths.
"""

_WHOLE_FILE_COMMANDS = frozenset({"cat", "less", "more", "bat"})
_BOUNDED_DEFAULT_COMMANDS = frozenset({"head", "tail"})
_SED_RANGE = re.compile(r"^(\d+)(?:,(\d+))?[a-z]$")
_UNMEASURABLE = ("*", "?", "$", "`", "~", "[")
_REDIRECTS = frozenset({">", ">>", "1>", "2>", "&>"})
_PIPE_TOKENS = frozenset({"|"})


def _last_stage_of_each_command(command: str) -> list[list[str]]:
    """Return the token list of every stage whose output reaches the agent.

    A stage followed by `|` feeds a filter; a command containing a redirect
    writes to disk. Neither reaches the agent, so neither is returned.
    """
    try:
        tokens = tokenize(command)
    except ValueError:
        return []

    stages: list[list[str]] = []
    current: list[str] = []
    piped_onward = False
    redirected = False

    def close(final: bool) -> None:
        nonlocal current, piped_onward, redirected
        if current and final and not piped_onward and not redirected:
            stages.append(current)
        current = []

    for word in tokens:
        if word in _PIPE_TOKENS:
            close(final=False)
            piped_onward = False
            continue
        if is_control_token(word):
            close(final=True)
            piped_onward = redirected = False
            continue
        if word in _REDIRECTS:
            redirected = True
            continue
        current.append(word)
    close(final=True)
    return stages


def _is_generated_dispatch_artifact(path: Path) -> bool:
    """Whether *path* is a run artifact written for an agent to read in one go.

    A task brief resolves every requirement it cites into full text precisely so
    the reading agent makes one read instead of many narrow ones. Charging that
    brief the same line budget as an arbitrary document would restore the
    per-slice cost it was written to remove, so the whole generated run-artifact
    tree under `RUNS_DIR` is outside the budget.
    """
    return RUNS_DIR.name in path.parts and RUNS_DIR.parent.name in path.parts


def _measurable_path(operand: str, cwd: str | None) -> Path | None:
    if not operand or operand.startswith("-"):
        return None
    if any(marker in operand for marker in _UNMEASURABLE):
        return None
    path = Path(operand)
    if not path.is_absolute() and cwd:
        path = Path(cwd) / path
    if not path.is_file() or _is_generated_dispatch_artifact(path):
        return None
    return path


def _line_count(path: Path) -> int | None:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").count("\n") + 1
    except OSError:
        return None


def _requested_lines(tokens: list[str], cwd: str | None) -> tuple[int, str] | None:
    """Return (lines this stage puts on screen, the file it reads), or None."""
    head = PurePosixPath(tokens[0]).name
    operands = [t for t in tokens[1:] if not t.startswith("-")]

    if head in _WHOLE_FILE_COMMANDS:
        return _whole_file_request(operands, cwd)
    if head in _BOUNDED_DEFAULT_COMMANDS:
        return _bounded_request(tokens, operands, cwd)
    if head == "sed":
        return _sed_request(tokens, operands, cwd)
    return None


def _whole_file_request(operands: list[str], cwd: str | None) -> tuple[int, str] | None:
    for operand in operands:
        path = _measurable_path(operand, cwd)
        if path is None:
            continue
        lines = _line_count(path)
        if lines is not None and lines > MAX_UNFILTERED_LINES:
            return lines, operand
    return None


def _explicit_count(tokens: list[str]) -> int | None:
    for index, token in enumerate(tokens):
        if token in ("-n", "-c") and index + 1 < len(tokens):
            digits = tokens[index + 1].lstrip("+-")
            return int(digits) if digits.isdigit() else None
        if re.fullmatch(r"-\d+", token):
            return int(token[1:])
    return None


def _bounded_request(
    tokens: list[str], operands: list[str], cwd: str | None
) -> tuple[int, str] | None:
    count = _explicit_count(tokens)
    if count is None or count <= MAX_UNFILTERED_LINES:
        return None
    target = next((o for o in operands if _measurable_path(o, cwd)), None)
    return (count, target) if target else None


def _sed_request(
    tokens: list[str], operands: list[str], cwd: str | None
) -> tuple[int, str] | None:
    if "-n" not in tokens:
        return None
    target = next((o for o in operands if _measurable_path(o, cwd)), None)
    if target is None:
        return None
    scripts = [o for o in operands if o != target]
    for script in scripts:
        match = _SED_RANGE.match(script)
        if match is None:
            continue
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        span = end - start + 1
        if span > MAX_UNFILTERED_LINES:
            return span, target
    return None


def build_file_dump_block_message(command: str, cwd: str | None = None) -> str | None:
    """Return a user-facing block reason for an oversized file dump, or None."""
    for tokens in _last_stage_of_each_command(command):
        stripped = strip_shell_wrappers(tokens)
        if not stripped:
            continue
        request = _requested_lines(stripped, cwd)
        if request is None:
            continue
        lines, target = request
        return (
            f"Blocked: this command puts {lines} lines of `{target}` into context in "
            f"one unfiltered read, over this project's {MAX_UNFILTERED_LINES}-line "
            "budget. Every line stays resident and is re-read on each later turn, so "
            "a wide peek is paid many times over. Read the range you actually need "
            "instead — the `Read` tool with `offset`/`limit`, or "
            "`sed -n '<start>,<end>p'` within the budget — or send the full output "
            "somewhere it does not reach context (pipe it through a filter, or "
            "redirect it to a file under `logs/` and read back only what matters). "
            "A glob, a variable, or a missing file is never blocked here."
        )
    return None
