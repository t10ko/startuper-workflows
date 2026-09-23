"""Test bootstrap: put the runtime package and the hook scripts on sys.path.

`agentic_workflows` sits at the repository root and is imported as a plain
top-level package, and the `.agents` scripts import each other as flat
top-level names, so tests import both the same way. With this conftest the
suite runs under a bare `uv run pytest tests` from the repository root.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = _ROOT / ".agents" / "scripts"

for _path in (str(_ROOT), str(_SCRIPTS)):
    if _path not in sys.path:
        sys.path.insert(0, _path)
