"""PreToolUse(Bash) guard: cap unfiltered file dumps at a 120-line budget."""

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

from agentic_workflows.file_dump_guard import build_file_dump_block_message


def main() -> None:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw else {}
    command = str(payload.get("tool_input", {}).get("command", ""))
    raw_cwd = payload.get("cwd")
    cwd = raw_cwd if isinstance(raw_cwd, str) else None
    message = build_file_dump_block_message(command, cwd)

    if message is None:
        return

    sys.stderr.write(f"{message}\n")
    raise SystemExit(2)


if __name__ == "__main__":
    main()
