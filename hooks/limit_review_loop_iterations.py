"""PreToolUse(Agent) cap: enforce code-review-fix-loop's --max-iterations.

Session state lives in the CONSUMER project's logs/ directory (anchored at
$CLAUDE_PROJECT_DIR), never next to this file — this script is typically a
symlink into a separate checkout of the agentic-workflows repo shared by
every consumer project, and each project owns its own iteration ledger.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _bootstrap_runtime() -> None:
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "src" / "agentic_workflows" / "__init__.py").is_file():
            sys.path.insert(0, str(candidate))
            return
    # Mirrors the original's behavior: a hook that cannot load exits nonzero
    # WITHOUT the block code, so the session proceeds past it (fail-open for
    # a cost cap, never for a safety guard). The stderr note keeps it visible.
    sys.stderr.write(
        "agentic_workflows runtime not found relative to "
        f"{Path(__file__).resolve()}; the iteration cap is not enforced this "
        "dispatch.\n"
    )
    raise SystemExit(1)


_bootstrap_runtime()

from agentic_workflows.review_loop_iterations import (
    decide_dispatch,
    load_ledger,
    store_ledger,
)
from agentic_workflows.time import utc_now


def project_dir() -> Path:
    return Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())


def extract_session_id(payload: dict[str, object]) -> str | None:
    for key in ("session_id", "sessionID", "conversation_id", "conversationID"):
        val = payload.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def extract_agent_types(payload: dict[str, object]) -> list[str]:
    types: list[str] = []
    tool_input = (
        payload.get("tool_input") or payload.get("arguments") or payload.get("input")
    )
    if isinstance(tool_input, dict):
        for key in ("subagent_type", "subagent_name", "TypeName", "subagent", "Role"):
            val = tool_input.get(key)
            if isinstance(val, str) and val:
                types.append(val)
                break

        subagents = tool_input.get("Subagents") or tool_input.get("subagents")
        if isinstance(subagents, list):
            for sub in subagents:
                if isinstance(sub, dict):
                    for key in (
                        "TypeName",
                        "subagent_type",
                        "subagent_name",
                        "subagent",
                        "Role",
                    ):
                        val = sub.get(key)
                        if isinstance(val, str) and val:
                            types.append(val)
                            break
    return types


def main() -> None:
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw else {}
    if not isinstance(payload, dict):
        return

    session_id = extract_session_id(payload)
    agent_types = extract_agent_types(payload)

    if not session_id or not agent_types:
        return

    state_path = project_dir() / "logs" / "review_loop_iterations.json"

    denial_reason: str | None = None
    for agent_type in agent_types:
        decision = decide_dispatch(
            load_ledger(state_path, session_id), agent_type, now=utc_now()
        )
        store_ledger(state_path, session_id, decision.ledger)
        if not decision.allowed:
            denial_reason = decision.reason
            break

    if denial_reason:
        sys.stderr.write(f"{denial_reason}\n")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
