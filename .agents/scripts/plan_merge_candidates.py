#!/usr/bin/env python3
"""Flag plan tasks whose shared files buy a wait the plan never needed.

A task group is the unit of parallelism: its tasks run one at a time inside
one checkout, and `scripts/parallel_plan_grouping.py`'s `label_groups`
downgrades a group to `Sequential (must follow <group>)` the moment its
declared files collide with another group's. So when the *same* file is
declared by tasks in two different groups, the resulting wait is bought by
how the plan was split rather than by the work.

The first repair is **single ownership**: give that file one owning task and
let the others depend on its result, which removes the collision without
growing any task. Fusing the tasks into one `## Task <N>` heading also
collapses the two groups -- and with them a wait, a review pass and a landing
merge -- but it is the last resort, reserved for two pieces neither of which
can be shown to work without the other, because fusing every task that shares
a hot file is how a plan grows one task nobody can review. Both rules, and why
this order, live in `.agents/rules/sizing-agent-work.md` §3.

This reads the Execution Queue's own declared lines rather than hand-invented
arguments, which is what `execution_grouping.md` requires before the grouping
counts as validated at all.

Measured 2026-09-21 on `docs/plans/2026-09-20-llm-stall-timeout-streaming-
transport.md`: six files were declared from two or three groups each, and
`src/llm/client/unified_client.py` alone chained groups 1, 2 and 5.

Run via: ``uv run python scripts/plan_merge_candidates.py <plan.md>``
Exit 0 when no file crosses a group boundary, 1 when one does.
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

import re
import sys
from pathlib import Path

from parallel_plan_grouping import (
    Task,
    files_shared_across_groups,
    label_groups,
    parse_sequential_label,
)

from agentic_workflows.markdown_fences import Fence, fence_lines

_TASK_HEADING = re.compile(r"^#+[ \t]+Task[ \t]+([0-9]+)")
_FIELD = re.compile(r"^-\s+`(Group|Files|Consumes|Produces)`:\s*(.*)$")
_BACKTICKED = re.compile(r"`([^`]+)`")


def _declared(raw: str) -> frozenset[str]:
    """Every backticked value on a field line, ignoring prose around them.

    A field's real values are always backticked in the Execution Queue's own
    format, and a `(none)` placeholder carries none -- so reading the
    backticks is what keeps a trailing explanatory clause from parsing as a
    file path.
    """
    return frozenset(_BACKTICKED.findall(raw))


def _unclosed_fence_line(fences: list[Fence]) -> int | None:
    """The one-indexed line a fence that never closes opens on, else `None`.

    A document ends inside a fence exactly when its last line is the opening
    line or an inner line of one; the fence that never closed is the last
    one opened.
    """
    if not fences or fences[-1] not in (Fence.OPENING, Fence.INSIDE):
        return None
    return 1 + max(
        index for index, fence in enumerate(fences) if fence is Fence.OPENING
    )


def parse_execution_queue(plan_text: str) -> list[Task]:
    """Every `## Task <N>` heading's declared grouping fields, in order.

    A task heading missing `Group` or `Files` raises rather than being
    skipped: a skipped task would let this gate report success over a plan it
    never actually checked, which is the concealment a green gate must never
    perform.

    A fenced block (`agentic_workflows.markdown_fences`) is quoted text: a task heading
    or a field line inside one starts no task and sets no field, so an example
    queue quoted in a plan cannot add a phantom task or overwrite a real one's
    field. For the same reason a fence that never closes raises: it would turn
    every task below it into quoted text and let the gate report on part of the
    plan.
    """
    lines = plan_text.splitlines()
    fences = fence_lines(lines)
    opened = _unclosed_fence_line(fences)
    if opened is not None:
        raise ValueError(
            f"The fenced block opened on line {opened} never closes, so every "
            "line after it would be read as quoted text and the tasks below it "
            "would go unchecked. Close the fence rather than let this gate "
            "report on part of the plan."
        )
    tasks: list[Task] = []
    fields: dict[str, str] = {}
    task_id: str | None = None

    def flush() -> None:
        if task_id is None:
            return
        for required in ("Group", "Files"):
            if required not in fields:
                raise ValueError(
                    f"Task {task_id} declares no `{required}` line, so its "
                    "grouping cannot be validated. Add the line to the plan's "
                    "Execution Queue rather than skipping the task."
                )
        tasks.append(
            Task(
                task_id=task_id,
                group_id=fields["Group"].strip(" `"),
                files=_declared(fields["Files"]),
                consumes=_declared(fields.get("Consumes", "")),
                produces=_declared(fields.get("Produces", "")),
                advisory_label=None,
            )
        )

    for line, fence in zip(lines, fences, strict=True):
        if fence is not Fence.OUTSIDE:
            continue
        heading = _TASK_HEADING.match(line)
        if heading:
            flush()
            task_id = heading.group(1)
            fields = {}
            continue
        field = _FIELD.match(line)
        if field and task_id is not None:
            fields[field.group(1)] = field.group(2)
    flush()
    return tasks


def report_lines(tasks: list[Task]) -> list[str]:
    """One line per file two or more groups both declare."""
    shared = files_shared_across_groups(tasks)
    owners = {
        path: sorted((task.task_id for task in tasks if path in task.files), key=int)
        for path in shared
    }
    return [
        f"{path}: groups {groups} via tasks {owners[path]}"
        for path, groups in shared.items()
    ]


def _task_counts(tasks: list[Task]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in tasks:
        counts[task.group_id] = counts.get(task.group_id, 0) + 1
    return counts


def longest_serial_chain(tasks: list[Task]) -> list[str]:
    """The groups whose tasks, run end to end, set the plan's wall clock.

    Groups run concurrently; a group's own tasks run one at a time in one
    worktree. The floor is therefore neither the group count nor the task
    count but the heaviest chain of dependent groups, each weighted by how
    many tasks it holds. A plan with twice the tasks and half this chain
    finishes sooner, and a task count alone would have called it worse --
    which is why `.agents/rules/sizing-agent-work.md` §3.3 judges a split by
    this number.
    """
    counts = _task_counts(tasks)
    dependencies = {
        group_id: parse_sequential_label(label)
        for group_id, label in label_groups(tasks).items()
    }

    def weight(chain: list[str]) -> int:
        return sum(counts[group_id] for group_id in chain)

    heaviest_to: dict[str, list[str]] = {}

    def chain_to(group_id: str) -> list[str]:
        if group_id not in heaviest_to:
            heaviest_to[group_id] = [group_id]
            upstream = max(
                (chain_to(leader) for leader in dependencies.get(group_id, ())),
                key=weight,
                default=[],
            )
            heaviest_to[group_id] = [*upstream, group_id]
        return heaviest_to[group_id]

    return max(
        (chain_to(group_id) for group_id in sorted(dependencies)),
        key=weight,
        default=[],
    )


def shape_lines(tasks: list[Task]) -> list[str]:
    """What the split costs in wall clock, and where the work piled up."""
    counts = _task_counts(tasks)
    chain = longest_serial_chain(tasks)
    depth = sum(counts[group_id] for group_id in chain)
    widest = max(sorted(counts), key=lambda group_id: counts[group_id])
    spelled = " -> ".join(f"{group_id}({counts[group_id]})" for group_id in chain)
    return [
        f"Serial chain: {spelled} = {depth} task{'' if depth == 1 else 's'} deep, "
        f"across {len(chain)} of {len(counts)} groups.",
        f"Widest group: {widest} holds {counts[widest]} of {len(tasks)} tasks, "
        "and they run one at a time.",
    ]


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        sys.stderr.write(
            "usage: uv run python scripts/plan_merge_candidates.py <plan.md>\n"
        )
        return 2

    tasks = parse_execution_queue(Path(args[0]).read_text(encoding="utf-8"))
    lines = report_lines(tasks)
    if tasks:
        sys.stdout.write("\n".join(shape_lines(tasks)) + "\n\n")
    if not lines:
        sys.stdout.write(
            f"{len(tasks)} tasks; no file is declared by more than one group.\n"
        )
        return 0

    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.write(
        f"\n{len(lines)} file(s) declared by more than one group. Each one "
        "forces a group to wait for another to merge before it can start. "
        "Give each named file one owning task the others consume, which "
        "removes the wait without growing any task; fuse the tasks only when "
        "neither can be shown to work without the other, or keep the split "
        "and say why in the plan.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
