"""PreToolUse(Edit|Write|NotebookEdit) guard: block writes into git's
administrative area and the per-user git configuration.

`PreToolUse` treats exit code 2 as "block this tool call" and EVERY other
code — 1 included — as a non-blocking error it proceeds past. An exception
escaping this hook would therefore PERMIT the write it was asked to judge, so
every failure below is converted to a block rather than allowed to propagate.
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
    from agentic_workflows.git_internals_edit_guard import (
        build_protected_edit_block_message,
    )
except Exception as exc:  # an unloadable guard must not open the gate
    sys.stderr.write(
        "Blocked: the protected-path edit guard could not be loaded "
        f"({type(exc).__name__}: {exc}).\n"
    )
    raise SystemExit(BLOCK_EXIT_CODE) from exc


def _block_message(raw: str) -> str | None:
    payload = json.loads(raw) if raw else {}
    tool_input = payload.get("tool_input", {})
    raw_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    file_path = Path(raw_path) if raw_path else None
    # A relative `file_path` is resolved by the tool layer against the working
    # directory the payload reports, never against whatever directory this hook
    # process was started in.
    raw_cwd = payload.get("cwd")
    cwd = Path(raw_cwd) if raw_cwd else None
    return build_protected_edit_block_message(file_path, cwd)


def main() -> int:
    try:
        message = _block_message(sys.stdin.read())
    except Exception as exc:  # noqa: BLE001 - fail closed, see BLOCK_EXIT_CODE
        sys.stderr.write(
            "Blocked: the protected-path edit guard could not decide this "
            f"path ({type(exc).__name__}: {exc}). Refusing rather than "
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
