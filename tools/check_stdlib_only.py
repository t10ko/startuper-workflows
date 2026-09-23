#!/usr/bin/env python3
"""Fail if any runtime module imports something outside the standard library.

The runtime (agentic_workflows/, .agents/hooks/, .agents/scripts/) must run
on plain python3 with no dependency install — consumers symlink it into
arbitrary-language repos. This is the enforcement behind that promise.
"""

from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCAN_DIRS = ("agentic_workflows", ".agents/hooks", ".agents/scripts")
ALLOWED_LOCAL = {"agentic_workflows"}


def local_imports(tree: ast.AST) -> list[str]:
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bad.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                continue  # relative import inside the same package
            if node.module:
                bad.append(node.module)
    return bad


def main() -> int:
    stdlib = set(sys.stdlib_module_names)
    # Sibling orchestration scripts import each other as flat top-level
    # modules (their bootstrap puts .agents/scripts on sys.path).
    sibling_scripts = {
        p.stem for p in (ROOT / ".agents" / "scripts").glob("*.py")
    }
    failures: list[str] = []
    checked = 0
    for dir_name in SCAN_DIRS:
        for path in sorted((ROOT / dir_name).rglob("*.py")):
            checked += 1
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for module in local_imports(tree):
                root_module = module.split(".")[0]
                if (
                    root_module in stdlib
                    or root_module in ALLOWED_LOCAL
                    or root_module in sibling_scripts
                ):
                    continue
                failures.append(f"{path.relative_to(ROOT)}: imports {module!r}")
    if failures:
        print("NON-STDLIB IMPORTS FOUND (runtime must stay stdlib-only):")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(f"stdlib-only check: {checked} files OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
