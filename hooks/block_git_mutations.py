"""PreToolUse(Bash) guard: block a specific set of dangerous git operations.

Run by Claude Code as `python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/<name>.py"`
with the hook payload on stdin. This file may be a symlink into a separate
checkout of the agentic-workflows repo; the bootstrap below resolves it and
puts that checkout's `src/` on sys.path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _bootstrap_runtime() -> None:
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "src" / "agentic_workflows" / "__init__.py").is_file():
            sys.path.insert(0, str(candidate))
            return
    # A blocking guard that cannot load must not open the gate: exit 2 blocks.
    sys.stderr.write(
        "Blocked: agentic_workflows runtime not found relative to "
        f"{Path(__file__).resolve()}; refusing to decide (fail closed).\n"
    )
    raise SystemExit(2)


_bootstrap_runtime()

from agentic_workflows.git_write_guard import build_git_danger_block_message


def main() -> None:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw else {}
    command = str(payload.get("tool_input", {}).get("command", ""))
    cwd_value = payload.get("cwd")
    cwd = Path(cwd_value) if cwd_value else None
    message = build_git_danger_block_message(command, cwd)

    if message is None:
        return

    sys.stderr.write(f"{message}\n")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
