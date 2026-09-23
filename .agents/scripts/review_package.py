"""Write a review package for one task's recorded `BASE..HEAD` range.

The package is a header, the commit list (`git log --oneline`), a
file-change summary (`git diff --stat`), and the full diff with ten lines of
context (`git diff -U10`) -- built from the task's *recorded* BASE, not
`HEAD~1`, so a multi-commit task's whole range reaches the reviewer rather
than only its last commit.

Default OUTFILE resolution reuses `scripts.sdd_workspace`'s own slug
derivation and git-root resolution directly (`derive_workspace_slug`,
`resolve_git_root`) rather than shelling out to a second copy of that
logic, per `.agents/rules/single-source-of-truth.md` -- the two scripts
share one slug-deriving implementation, never two. The workspace
directory itself is still created here (`mkdir(parents=True,
exist_ok=True)`, matching `sdd_workspace.py`'s own call): this script must
stay a freestanding entry point that can create its output directory
without requiring `sdd_workspace.py` to have run first in the same process.
"""

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
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from sdd_workspace import (
    GitRootUnavailableError,
    derive_workspace_slug,
    resolve_git_root,
)
from agentic_workflows.plan_run_paths import RUNS_DIR


def _git_executable() -> str:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise RuntimeError("Executable 'git' not found in PATH")
    return git_executable


def _commit_exists(git_executable: str, commit: str) -> bool:
    result = subprocess.run(
        [git_executable, "rev-parse", "--verify", "--quiet", commit],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _git_output(git_executable: str, *args: str) -> str:
    result = subprocess.run(
        [git_executable, *args],
        stdout=subprocess.PIPE,
        text=True,
        check=True,
    )
    return result.stdout


def _short_sha(git_executable: str, commit: str) -> str:
    return _git_output(git_executable, "rev-parse", "--short", commit).strip()


def _commit_count(git_executable: str, base: str, head: str) -> int:
    return int(
        _git_output(git_executable, "rev-list", "--count", f"{base}..{head}").strip()
    )


def _default_outfile(
    plan: Path, base: str, head: str, git_executable: str
) -> Path | None:
    """Resolve (creating if needed) the default OUTFILE path.

    Returns `None` when `sdd_workspace.derive_workspace_slug` cannot derive a
    workspace name from *plan* -- the caller reports that as its own exit-2
    condition, since a package with nowhere to land is a failed run, not a
    run that quietly writes somewhere else.
    """
    slug = derive_workspace_slug(plan)
    if slug is None:
        return None
    workspace_dir = resolve_git_root() / RUNS_DIR / slug
    workspace_dir.mkdir(parents=True, exist_ok=True)
    base_short = _short_sha(git_executable, base)
    head_short = _short_sha(git_executable, head)
    return workspace_dir / f"review-{base_short}..{head_short}.diff"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="review_package",
        description=(
            "Generate a review package (commit list, stat summary, and "
            "full diff) for one plan's BASE..HEAD range."
        ),
    )
    parser.add_argument("plan", type=Path, help="Path to the plan file.")
    parser.add_argument("base", help="The base commit (exclusive).")
    parser.add_argument("head", help="The head commit (inclusive).")
    parser.add_argument(
        "outfile",
        type=Path,
        nargs="?",
        default=None,
        help="Output file path. Defaults under the plan's sdd workspace.",
    )
    args = parser.parse_args(argv)
    plan: Path = args.plan
    base: str = args.base
    head: str = args.head
    outfile: Path | None = args.outfile

    if not plan.is_file():
        sys.stderr.write(f"no such plan file: {plan.as_posix()}\n")
        return 2

    git_executable = _git_executable()
    if not _commit_exists(git_executable, base):
        sys.stderr.write(f"bad BASE: {base}\n")
        return 2
    if not _commit_exists(git_executable, head):
        sys.stderr.write(f"bad HEAD: {head}\n")
        return 2

    if outfile is None:
        try:
            resolved = _default_outfile(plan, base, head, git_executable)
        except GitRootUnavailableError as exc:
            sys.stderr.write(exc.stderr)
            return exc.returncode
        if resolved is None:
            sys.stderr.write(
                f"cannot derive a workspace name from: {plan.as_posix()}\n"
            )
            return 2
        outfile = resolved

    commit_range = f"{base}..{head}"
    log_output = _git_output(git_executable, "log", "--oneline", commit_range)
    stat_output = _git_output(git_executable, "diff", "--stat", commit_range)
    diff_output = _git_output(git_executable, "diff", "-U10", commit_range)
    content = (
        f"# Review package: {base}..{head}\n\n"
        f"## Commits\n{log_output}\n"
        f"## Files changed\n{stat_output}\n"
        f"## Diff\n{diff_output}"
    )
    outfile.write_text(content, encoding="utf-8")

    commits = _commit_count(git_executable, base, head)
    size = outfile.stat().st_size
    # `scripts/` CLIs print their own contract output; task-constraints.md
    # names this as the one permitted `print()` use in this repository, but
    # no `scripts/**/*.py` ruff per-file-ignore exists for T201 (only
    # `tests/**/*.py` has one), so the exemption is documented inline here.
    print(f"wrote {outfile.as_posix()}: {commits} commit(s), {size} bytes")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
