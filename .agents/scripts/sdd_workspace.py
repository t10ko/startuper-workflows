"""Resolve one plan's workspace directory and print its absolute path.

Creates, if it is not already there, the working-tree directory that holds
one plan's short-lived artifacts -- task briefs, implementer reports, review
packages -- and prints that directory's absolute path. Every workflow that
dispatches work task by task resolves the workspace through this one entry
point, so a brief written in one step and read back in a later one always
name the same directory.

`RUNS_DIR` is imported from `agentic_workflows.plan_run_paths`, never restated, per
`.agents/rules/single-source-of-truth.md`.

Two things this deliberately does not do:

- It writes no self-ignoring `.gitignore` under the run-artifact root. A
  tracked ignore-file entry for `docs/runs/` is the single owner of that rule.
- It creates no `progress.md`. The workflow that consumes this directory
  writes that file itself and is its only writer.
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

import argparse
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from agentic_workflows.plan_run_paths import RUNS_DIR

_PLAN_SUFFIX = ".md"
_UNDERIVABLE_NAMES = frozenset({".", ".."})


class GitRootUnavailableError(Exception):
    """`resolve_git_root()`'s underlying `git rev-parse --show-toplevel`
    call exited nonzero -- most commonly because the current directory is
    not inside a git repository at all.

    Carries git's own exit code and stderr message verbatim so a caller can
    surface git's one-line fatal message and nothing else, instead of letting
    an uncaught `CalledProcessError` reach the interpreter's own top-level
    handler and print a Python traceback.
    """

    def __init__(self, returncode: int, stderr: str) -> None:
        super().__init__(stderr)
        self.returncode = returncode
        self.stderr = stderr


def derive_workspace_slug(plan: Path) -> str | None:
    """Replicate POSIX `basename PATH .md` semantics for a plan's slug.

    The `.md` suffix is stripped only when the name is not identical to the
    suffix itself -- matching `basename`'s own "if suffix equals string, it
    is not removed" rule -- and only ever removes a trailing occurrence.
    Returns `None` when no usable slug can be derived: an empty name, or
    the sentinel names `.` / `..`.
    """
    name = plan.name
    if name != _PLAN_SUFFIX and name.endswith(_PLAN_SUFFIX):
        name = name[: -len(_PLAN_SUFFIX)]
    if not name or name in _UNDERIVABLE_NAMES:
        return None
    return name


def resolve_git_root() -> Path:
    """The current git repository's top-level directory.

    Read live on every call, never cached or hardcoded: inside a linked
    worktree, this is that worktree's own root, exactly as
    `git rev-parse --show-toplevel` itself resolves it. Raises
    `GitRootUnavailableError` -- carrying git's own exit code and stderr
    message -- when the underlying git call exits nonzero, most commonly
    because the current directory is not inside a git repository at all.
    """
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError("Executable 'git' not found in PATH")
    result = subprocess.run(
        [git_executable, "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitRootUnavailableError(result.returncode, result.stderr)
    return Path(result.stdout.strip())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sdd_workspace",
        description=(
            "Resolve (creating if needed) the working-tree directory a "
            "plan's short-lived run artifacts live under, and print its "
            "absolute path."
        ),
    )
    parser.add_argument("plan", type=Path, help="Path to the plan file.")
    args = parser.parse_args(argv)
    plan: Path = args.plan

    if not plan.is_file():
        sys.stderr.write(f"no such plan file: {plan.as_posix()}\n")
        return 2

    slug = derive_workspace_slug(plan)
    if slug is None:
        sys.stderr.write(f"cannot derive a workspace name from: {plan.as_posix()}\n")
        return 2

    try:
        workspace_dir = resolve_git_root() / RUNS_DIR / slug
    except GitRootUnavailableError as exc:
        sys.stderr.write(exc.stderr)
        return exc.returncode

    workspace_dir.mkdir(parents=True, exist_ok=True)
    # `scripts/` CLIs print their own contract output; task-constraints.md
    # names this as the one permitted `print()` use in this repository, but
    # no `scripts/**/*.py` ruff per-file-ignore exists for T201 (only
    # `tests/**/*.py` has one), so the exemption is documented inline here.
    print(workspace_dir.as_posix())  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
