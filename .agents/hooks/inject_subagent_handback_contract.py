"""SubagentStart hook: inject the handback contract into read-only agents.

Context-only by the event's contract: its output cannot block a spawn, so a
missing runtime fails open with a stderr note rather than blocking anything.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _bootstrap_runtime() -> None:
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "agentic_workflows" / "__init__.py").is_file():
            sys.path.insert(0, str(candidate))
            return
    sys.stderr.write(
        "agentic_workflows runtime not found relative to "
        f"{Path(__file__).resolve()}; handback contract not injected.\n"
    )
    raise SystemExit(0)


_bootstrap_runtime()

from agentic_workflows.agent_handback_contract import build_handback_contract_context


def main() -> None:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw else {}
    agent_type = payload.get("agent_type")
    context = build_handback_contract_context(
        agent_type if isinstance(agent_type, str) else None
    )

    if context is None:
        return

    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SubagentStart",
                    "additionalContext": context,
                }
            }
        )
    )


if __name__ == "__main__":
    main()
