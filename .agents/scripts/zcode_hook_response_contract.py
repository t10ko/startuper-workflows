"""ZCode hook wrapper: emit the response contract as strict-JSON additionalContext.

REQ-008 / spec D-004 in
``docs/specs/2026-09-22-continuous-dispatch-and-zcode-reporting.md``: the hook
invokes this wrapper; its whole authority is reading
``.agents/rules/response-contract.md`` live and writing one strict-JSON
``{"additionalContext": "<contract content>"}`` object to stdout for the client
to inject. It writes nothing else anywhere and imports nothing outside the
standard library, so a hook can run it with a bare interpreter.

Failure contract: the contract path resolves from this file's own location,
never from the hook's working directory (which is the client's choice). Any
read failure propagates: stdout stays empty, the traceback lands on stderr,
and the non-zero exit tells the client to inject nothing. No stderr is
suppressed and success is never forced; the session stays silent and the
binding read-once directive in root ``AGENTS.md`` §11 remains in force.
"""

from __future__ import annotations


# --- standalone bootstrap -------------------------------------------------
# This script may run from a consumer repo via symlink; resolve its real
# location and put both the runtime root and the sibling-script directory on
# sys.path before any agentic_workflows/sibling imports run.
def _bootstrap() -> None:
    import sys as _sys
    from pathlib import Path as _Path
    here = _Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "agentic_workflows" / "__init__.py").is_file():
            _sys.path.insert(0, str(candidate))
            break
    if str(here) not in _sys.path:
        _sys.path.insert(0, str(here))


_bootstrap()
# --------------------------------------------------------------------------

import json
import sys
from pathlib import Path

CONTRACT_PATH = (
    Path(__file__).resolve().parents[1] / ".agents/rules/response-contract.md"
)


def read_contract() -> str:
    """Read the contract live; any read failure propagates, injecting nothing."""
    return CONTRACT_PATH.read_text(encoding="utf-8")


def main() -> int:
    payload = json.dumps({"additionalContext": read_contract()})
    sys.stdout.write(payload + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
