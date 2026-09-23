from __future__ import annotations

# --- standalone bootstrap -------------------------------------------------
# This script may run from a consumer repo via symlink; resolve its real
# location and put both the runtime root and the sibling-script directory on
# sys.path before any agentic_workflows/sibling imports run.
def _bootstrap() -> None:
    import sys as _sys
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "agentic_workflows" / "__init__.py").is_file():
            _sys.path.insert(0, str(candidate))
            break
    if str(here) not in _sys.path:
        _sys.path.insert(0, str(here))


_bootstrap()
# --------------------------------------------------------------------------

import argparse
import importlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
project_root_str = str(PROJECT_ROOT)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract Python antipatterns and suspicious optional-arg shims.",
    )
    parser.add_argument(
        "--scope",
        choices=["src", "src-tooling"],
        default="src-tooling",
        help="Scan scope for the extraction report.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Markdown file path to write.",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        type=Path,
        default=[],
        help="Specific files or directories to scan. Overrides --scope when present.",
    )
    return parser.parse_args()


def main() -> int:
    scanner_module = importlib.import_module("agentic_workflows.python_antipattern_scanner")
    args = _parse_args()
    if args.paths:
        report = scanner_module.build_paths_antipattern_report(Path.cwd(), args.paths)
    else:
        report = scanner_module.build_repo_antipattern_report(
            Path.cwd(), scope=args.scope
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        scanner_module.render_markdown_report(report),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
