"""InstructionsLoaded hook: append every instruction-file load to a JSONL log.

Observational only — this event has no output fields and its exit code is
ignored, so it CANNOT filter or block a rule from loading. The log lives in
the CONSUMER project's logs/ directory ($CLAUDE_PROJECT_DIR), since this
script is typically a symlink into a shared checkout of the
agentic-workflows repo.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _bootstrap_runtime() -> None:
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "agentic_workflows" / "__init__.py").is_file():
            sys.path.insert(0, str(candidate))
            return
    # Observational: a missing runtime must not disturb the session.
    sys.stderr.write(
        "agentic_workflows runtime not found relative to "
        f"{Path(__file__).resolve()}; instruction loads not logged.\n"
    )
    raise SystemExit(0)


_bootstrap_runtime()

from agentic_workflows.instructions_loaded_log import (
    append_instructions_loaded_record,
    build_instructions_loaded_record,
)


def main() -> None:
    record = build_instructions_loaded_record(sys.stdin.read())
    if record is None:
        return
    project_dir = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
    append_instructions_loaded_record(
        record, project_dir / "logs" / "instructions_loaded.jsonl"
    )


if __name__ == "__main__":
    main()
