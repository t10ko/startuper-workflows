"""PreToolUse(Bash) guard: block shell-issued writes into protected path
classes (git's administrative area, the per-user git configuration, and
plan-run authorization records).

`PreToolUse` treats exit code 2 as "block this tool call" and EVERY other
code — 1 included — as a non-blocking error it proceeds past. An exception
escaping this hook would therefore PERMIT the command it was asked to judge,
so every failure below is converted to a block rather than allowed to
propagate.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BLOCK_EXIT_CODE = 2
ALLOW_EXIT_CODE = 0

try:
    _here = Path(__file__).resolve().parent
    for _candidate in (_here, *_here.parents):
        if (_candidate / "src" / "agentic_workflows" / "__init__.py").is_file():
            sys.path.insert(0, str(_candidate))
            break
    else:
        raise ImportError("agentic_workflows runtime not found")
    from agentic_workflows.protected_path_write_guard import (
        build_protected_path_write_block_message,
    )
except Exception as exc:  # an unloadable guard must not open the gate
    sys.stderr.write(
        "Blocked: the protected-path write guard could not be loaded "
        f"({type(exc).__name__}: {exc}).\n"
    )
    raise SystemExit(BLOCK_EXIT_CODE) from exc


def _block_message(raw: str) -> str | None:
    payload = json.loads(raw) if raw else {}
    command = payload.get("tool_input", {}).get("command", "")
    if not isinstance(command, str):
        raise TypeError(f"tool_input.command is {type(command).__name__}, not str")
    # The shell resolves a relative operand against the working directory the
    # payload reports, never against whatever directory this hook process was
    # started in. A non-string `cwd` is not a usable base and must not be
    # silently read as "no base given".
    raw_cwd = payload.get("cwd")
    if raw_cwd is not None and not isinstance(raw_cwd, str):
        raise TypeError(f"cwd is {type(raw_cwd).__name__}, not str")
    cwd = Path(raw_cwd) if raw_cwd else None
    return build_protected_path_write_block_message(command, cwd)


def main() -> int:
    try:
        message = _block_message(sys.stdin.read())
    except Exception as exc:  # noqa: BLE001 - fail closed, see BLOCK_EXIT_CODE
        sys.stderr.write(
            "Blocked: the protected-path write guard could not decide this "
            f"command ({type(exc).__name__}: {exc}). Refusing rather than "
            "permitting a write that may land inside git's administrative "
            "area or on a plan-run authorization record.\n"
        )
        return BLOCK_EXIT_CODE

    if message is None:
        return ALLOW_EXIT_CODE

    sys.stderr.write(f"{message}\n")
    return BLOCK_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
