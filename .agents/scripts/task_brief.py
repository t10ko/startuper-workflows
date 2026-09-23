"""Extract one task's full text from an implementation plan into a file.

Writes the task's own section of the plan to `task-<N>-brief.md` in the
plan's workspace, so the task text never has to be pasted through an
orchestrating agent's own context: the agent sends the path, and the agent
it dispatches reads the file.

The default output path is derived by importing `scripts.sdd_workspace`'s
own `derive_workspace_slug` and `resolve_git_root` -- the single owners of
that resolution logic -- and composing them with the single-owner
`RUNS_DIR`, rather than re-deriving a workspace directory independently,
per `.agents/rules/single-source-of-truth.md`.

A failed extraction writes no file at all. The output file is created only
after at least one line has been extracted, so a caller that checks whether
the brief file exists to decide whether extraction succeeded can never find
a stale or zero-byte one left behind by a run that matched no heading.
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
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from sdd_workspace import (
    GitRootUnavailableError,
    derive_workspace_slug,
    resolve_git_root,
)
from agentic_workflows.markdown_fences import Fence, fence_lines
from agentic_workflows.plan_references import (
    Reference,
    linked_document_paths,
    resolve_citations,
)
from agentic_workflows.plan_run_paths import RUNS_DIR

_ANY_TASK_HEADING = re.compile(r"^#+[ \t]+Task[ \t]+[0-9]+")


def _task_heading_pattern(task_number: str) -> re.Pattern[str]:
    """The heading regex for exactly *task_number*.

    Matches `Task 5` at any heading depth but never `Task 50`: the
    character immediately after the number must be non-digit or
    end-of-line. *task_number* is kept as `str`, not parsed as `int`, so a
    non-numeric argument reaches this same matching path and correctly
    matches nothing, rather than failing argument parsing with a different
    error for what is the same outcome: no such task in this plan.

    *task_number* is a command-line string, so it is matched as text
    (`re.escape`): a `.`, `*`, `|` or bracket in it is that character, never
    regex syntax. Otherwise `1.*` would name every task and `(` would fail
    with a `re.error` traceback instead of reaching the not-found path.
    """
    return re.compile(rf"^#+[ \t]+Task[ \t]+{re.escape(task_number)}([^0-9]|$)")


def extract_task_section(plan_text: str, task_number: str) -> list[str]:
    """Every line from the heading matching *task_number* up to (not
    including) the next task heading of any number.

    A heading inside a fenced block (`agentic_workflows.markdown_fences`) is quoted
    text and neither starts nor ends a section, so a code sample demonstrating
    heading syntax is never mistaken for a real task boundary; the fence's own
    lines belong to the section that holds them. Returns an empty list when no
    heading matches *task_number*.
    """
    specific_pattern = _task_heading_pattern(task_number)
    lines = plan_text.splitlines()
    in_task = False
    extracted: list[str] = []
    for line, fence in zip(lines, fence_lines(lines), strict=True):
        if fence is Fence.OUTSIDE and _ANY_TASK_HEADING.match(line):
            in_task = bool(specific_pattern.match(line))
        if in_task:
            extracted.append(line)
    return extracted


def source_documents(plan: Path, plan_text: str) -> dict[Path, str]:
    """The plan and every readable document its header links, in search order.

    The plan comes first so its own narrower restatement of an identifier wins
    over the specification's broader one. A linked path that does not resolve to
    a readable file is skipped rather than raising: a plan may link a document
    that has not been written, and a brief missing one source is still worth far
    more than no brief.
    """
    documents: dict[Path, str] = {plan: plan_text}
    base = plan.parent
    for target in linked_document_paths(plan_text).values():
        for candidate in (target, base / target, Path.cwd() / target):
            if candidate.is_file():
                documents.setdefault(candidate, candidate.read_text(encoding="utf-8"))
                break
    return documents


def _reference_section(resolved: list[Reference], unresolved: list[str]) -> list[str]:
    """The brief's resolved-definition and unresolved-citation sections.

    Empty when the task cites nothing, so a plan with no identifiers produces
    exactly the task's own text and nothing else.
    """
    if not resolved and not unresolved:
        return []
    lines = [
        "",
        "---",
        "",
        "## Referenced definitions",
        "",
        "Every identifier this task cites is reproduced below, verbatim from the",
        "document that owns it. Read nothing else to learn what this task must",
        "satisfy.",
    ]
    for reference in resolved:
        # An attribution line rather than a wrapping heading: a definition that is
        # itself a heading block would otherwise appear under a near-identical
        # heading of its own, twice.
        lines += [
            "",
            f"`{reference.identifier}` — from `{reference.source.as_posix()}`:",
            "",
            reference.text,
        ]
    if unresolved:
        lines += [
            "",
            "## Unresolved citations",
            "",
            "These identifiers are cited by this task and defined by no document the",
            "plan links. Treat each as a gap in the plan, not as work to invent.",
            "",
        ]
        lines += [f"- `{identifier}`" for identifier in unresolved]
    return lines


def _default_output_path(plan: Path, task_number: str) -> Path | None:
    """The default `<workspace>/task-<N>-brief.md` path for *task_number*.

    Composes `sdd_workspace`'s own slug-derivation and git-root resolution
    -- imported, not duplicated -- with the single-owner `RUNS_DIR`, then
    creates the workspace directory idempotently, matching what running
    `sdd_workspace.py` directly would do. Returns `None` when no slug can
    be derived from *plan*, mirroring that script's own failure mode.
    """
    slug = derive_workspace_slug(plan)
    if slug is None:
        return None
    workspace_dir = resolve_git_root() / RUNS_DIR / slug
    workspace_dir.mkdir(parents=True, exist_ok=True)
    return workspace_dir / f"task-{task_number}-brief.md"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="task_brief",
        description=(
            "Extract one task's full text from an implementation plan into "
            "a file, so the task text never has to be pasted through the "
            "controller's context."
        ),
    )
    parser.add_argument("plan", type=Path, help="Path to the plan file.")
    parser.add_argument(
        "task_number",
        help="The task number to extract (kept as text, matching the "
        "original's untyped shell argument).",
    )
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=None,
        help="Output file path (default: <workspace>/task-<N>-brief.md).",
    )
    args = parser.parse_args(argv)
    plan: Path = args.plan
    task_number: str = args.task_number

    if not plan.is_file():
        sys.stderr.write(f"no such plan file: {plan.as_posix()}\n")
        return 2

    output: Path | None = args.output
    if output is None:
        try:
            output = _default_output_path(plan, task_number)
        except GitRootUnavailableError as exc:
            sys.stderr.write(exc.stderr)
            return exc.returncode
        if output is None:
            sys.stderr.write(
                f"cannot derive a workspace name from: {plan.as_posix()}\n"
            )
            return 2

    plan_text = plan.read_text(encoding="utf-8")
    lines = extract_task_section(plan_text, task_number)
    if not lines:
        sys.stderr.write(
            f"task {task_number} not found in {plan.as_posix()} "
            f"(no heading matching 'Task {task_number}')\n"
        )
        return 3

    resolved, unresolved = resolve_citations(
        "\n".join(lines), source_documents(plan, plan_text)
    )
    lines = lines + _reference_section(resolved, unresolved)
    if unresolved:
        sys.stderr.write(
            f"task {task_number} cites {len(unresolved)} identifier(s) no linked "
            f"document defines: {', '.join(unresolved)}\n"
        )

    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # `scripts/` CLIs print their own contract output; task-constraints.md
    # names this as the one permitted `print()` use in this repository, but
    # no `scripts/**/*.py` ruff per-file-ignore exists for T201 (only
    # `tests/**/*.py` has one), so the exemption is documented inline here,
    # matching `scripts/sdd_workspace.py`'s own precedent.
    print(f"wrote {output.as_posix()}: {len(lines)} lines")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
