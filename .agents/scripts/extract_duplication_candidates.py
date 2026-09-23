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
        description=(
            "Scan the current diff's touched paths (plus bounded "
            "same-directory siblings, REQ-007) for duplication via jscpd, "
            "and write a markdown candidate report for the D-C review "
            "dimension (dimension 11 of code-review-fix-loop)."
        ),
    )
    parser.add_argument(
        "--paths",
        nargs="+",
        type=Path,
        required=True,
        help="Touched file paths from the scoped diff (REQ-007).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Markdown file path to write.",
    )
    parser.add_argument(
        "--min-tokens",
        type=int,
        default=None,
        help="Override jscpd's --min-tokens threshold (REQ-015 default if omitted).",
    )
    parser.add_argument(
        "--min-lines",
        type=int,
        default=None,
        help="Override jscpd's --min-lines threshold (REQ-015 default if omitted).",
    )
    return parser.parse_args()


def main() -> int:
    scanner_module = importlib.import_module("agentic_workflows.duplication_scanner")
    args = _parse_args()
    project_root = Path.cwd()

    kwargs: dict[str, int] = {}
    if args.min_tokens is not None:
        kwargs["min_tokens"] = args.min_tokens
    if args.min_lines is not None:
        kwargs["min_lines"] = args.min_lines

    report = scanner_module.build_duplication_report(
        project_root=project_root,
        touched_paths=args.paths,
        jscpd_output_dir=project_root / "verify" / "duplication_reports" / "_jscpd_raw",
        **kwargs,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        scanner_module.render_markdown_report(report),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
