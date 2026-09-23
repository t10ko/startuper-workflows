"""Deterministic helpers for parallel-safety grouping of implementation-plan tasks.

Used by the `parallel-subagent-driven-development` skill
(`.agents/skills/parallel-subagent-driven-development/SKILL.md`) and by
`detailed-plan.md`'s Execution Queue to label task groups `Independent
(parallel-safe)` or `Sequential (must follow <group>)`, to detect actual
changed-file overlap before a merge, to gate a `Sequential` group's dispatch
on its dependencies' merge state, to attribute a post-merge `make verify`
failure to a single owning group, and to decide whether worktree creation
must halt. Every function here is a pure, deterministic check with no file
or process I/O — the orchestrating agent session supplies the inputs.
"""

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


import itertools
import re
from collections.abc import Iterable
from typing import NamedTuple

INDEPENDENT_LABEL = "Independent (parallel-safe)"
MERGED_STATE = "Merged"


class Task(NamedTuple):
    """One implementation-plan task as declared in the Execution Queue.

    `advisory_label`, if present, is the full pre-formatted label a linked
    task-spec's §22 table already assigned this task's group (e.g.
    `"Independent (parallel-safe)"` or `"Sequential (must follow AB)"`). It
    is advisory only (REQ-003): re-validated against `files`, `consumes`,
    and `produces`, never trusted as-is.
    """

    task_id: str
    group_id: str
    files: frozenset[str]
    consumes: frozenset[str]
    produces: frozenset[str]
    advisory_label: str | None


def _build_group_dependencies(
    tasks: list[Task],
) -> tuple[list[str], dict[str, frozenset[str]], dict[str, str | None]]:
    group_files: dict[str, frozenset[str]] = {}
    group_consumes: dict[str, frozenset[str]] = {}
    group_produces: dict[str, frozenset[str]] = {}
    group_advisory: dict[str, str | None] = {}

    for task in tasks:
        group_files[task.group_id] = (
            group_files.get(task.group_id, frozenset()) | task.files
        )
        group_consumes[task.group_id] = (
            group_consumes.get(task.group_id, frozenset()) | task.consumes
        )
        group_produces[task.group_id] = (
            group_produces.get(task.group_id, frozenset()) | task.produces
        )
        group_advisory.setdefault(task.group_id, task.advisory_label)

    group_ids = sorted(group_files)
    collected: dict[str, set[str]] = {}
    for first_id, second_id in itertools.combinations(group_ids, 2):
        if actual_diff_overlaps(group_files[first_id], group_files[second_id]):
            leader, follower = sorted((first_id, second_id))
            collected.setdefault(follower, set()).add(leader)
        if group_consumes[second_id] & group_produces[first_id]:
            collected.setdefault(second_id, set()).add(first_id)
        if group_consumes[first_id] & group_produces[second_id]:
            collected.setdefault(first_id, set()).add(second_id)

    for group_id in group_ids:
        if group_id not in collected:
            advisory = group_advisory.get(group_id)
            if advisory is not None and advisory.startswith("Sequential"):
                named = parse_sequential_label(advisory)
                if named:
                    collected[group_id] = set(named)

    dependency = {
        group_id: frozenset(leaders) for group_id, leaders in collected.items()
    }

    cycle = _find_dependency_cycle(dependency)
    if cycle is not None:
        chain = " -> ".join([*cycle, cycle[0]])
        raise ValueError(
            f"Circular Sequential dependency detected between groups: {chain}. "
            "This plan cannot be auto-labeled; escalate to a human to fix the "
            "grouping before dispatch."
        )

    return group_ids, dependency, group_advisory


def files_shared_across_groups(tasks: list[Task]) -> dict[str, list[str]]:
    """Every declared file two or more groups both edit, with those groups.

    One file inside one group costs nothing: a group is precisely the set of
    tasks that share files, and they already run one at a time in one
    checkout. The same file in *two* groups is what downgrades one of them to
    `Sequential`, so the wait is bought by how the plan was split rather than
    by the work itself -- merging those tasks into one task collapses the two
    groups, and with them a wait, a review pass and a landing merge.

    Measured 2026-09-21 on `docs/plans/2026-09-20-llm-stall-timeout-streaming-
    transport.md`: six files were edited from two or three groups each, and
    `src/llm/client/unified_client.py` alone chained three of them.
    """
    owners: dict[str, set[str]] = {}
    for task in tasks:
        for path in task.files:
            owners.setdefault(path, set()).add(task.group_id)
    return {
        path: sorted(groups)
        for path, groups in sorted(owners.items())
        if len(groups) > 1
    }


def label_groups(tasks: list[Task]) -> dict[str, str]:
    """Label every group `Independent (parallel-safe)` or `Sequential (must
    follow <group>)` (REQ-002/REQ-003).

    File-path overlap across two groups is the primary signal; a `Consumes`
    naming a signature only another group's task `Produces` is the secondary
    signal. Either signal collision downgrades the affected group(s) to
    `Sequential`, overriding any advisory label. When neither signal
    collides, an advisory `Sequential` label is preserved as-is — it is
    never upgraded to `Independent` — and a group with no advisory label at
    all defaults to `Independent`.

    Raises `ValueError` if the derived dependencies form a cycle (e.g. two
    groups' Consumes/Produces sets mutually reference each other). A cycle
    means no group in it could ever reach `Merged` first, so
    `dependency_wait_satisfied()` would poll forever — this is a defective
    upstream plan that must never be silently labeled; it must halt and be
    escalated to a human instead.
    """
    group_ids, dependency, group_advisory = _build_group_dependencies(tasks)
    labels: dict[str, str] = {}
    for group_id in group_ids:
        if group_id in dependency:
            labels[group_id] = _sequential_label(dependency[group_id])
            continue
        advisory = group_advisory.get(group_id)
        if advisory is not None and advisory.startswith("Sequential"):
            labels[group_id] = advisory
        else:
            labels[group_id] = INDEPENDENT_LABEL
    return labels


def calculate_critical_path(tasks: list[Task]) -> list[str]:
    """Return the list of group IDs on the longest sequential dependency chain.

    Traces upstream dependencies for each group and identifies the chain with
    maximum depth. Used by detailed-plan and task-spec to highlight the critical
    path so planners can de-bloat bottleneck groups.
    """
    if not tasks:
        return []
    group_ids, dependency, _ = _build_group_dependencies(tasks)
    longest_from: dict[str, list[str]] = {}

    def deepest_chain(group_id: str) -> list[str]:
        if group_id in longest_from:
            return longest_from[group_id]
        longest_from[group_id] = [group_id]
        best: list[str] = []
        for leader in sorted(dependency.get(group_id, frozenset())):
            candidate = deepest_chain(leader)
            if len(candidate) > len(best):
                best = candidate
        longest_from[group_id] = [*best, group_id]
        return longest_from[group_id]

    longest_path: list[str] = []
    for group_id in group_ids:
        chain = deepest_chain(group_id)
        if len(chain) > len(longest_path):
            longest_path = chain

    return longest_path


def calculate_execution_waves(
    labels: dict[str, str],
    max_concurrent_agents: int | None = None,
) -> list[list[str]]:
    """Partition labeled groups into execution waves respecting dependencies
    and the concurrency cap (currently max 5 concurrent agents from AGENTS.md).

    Wave 0: Any pre-flight bootstrap groups (e.g. group ID starting with '0' or labeled Wave 0).
    Wave 1+: Independent and newly unblocked sequential groups.
    If a wave exceeds `max_concurrent_agents`, it is partitioned into sub-batches
    of size <= max_concurrent_agents.
    """
    if not labels:
        return []

    group_deps: dict[str, tuple[str, ...]] = {
        group_id: parse_sequential_label(label)
        if label.startswith("Sequential")
        else ()
        for group_id, label in labels.items()
    }

    wave_levels: dict[str, int] = {}

    def get_wave_level(gid: str, visited: set[str]) -> int:
        if gid in wave_levels:
            return wave_levels[gid]
        if gid in visited:
            return 1
        visited.add(gid)
        known = [dep for dep in group_deps.get(gid, ()) if dep in group_deps]
        if not known:
            level = (
                0
                if gid.startswith("0") or "wave 0" in labels.get(gid, "").lower()
                else 1
            )
        else:
            level = max(get_wave_level(dep, visited) + 1 for dep in known)
            level = max(1, level)
        wave_levels[gid] = level
        return level

    for gid in sorted(labels.keys()):
        get_wave_level(gid, set())

    grouped_by_level: dict[int, list[str]] = {}
    for gid in sorted(labels.keys()):
        level = wave_levels[gid]
        grouped_by_level.setdefault(level, []).append(gid)

    waves: list[list[str]] = []
    for level in sorted(grouped_by_level.keys()):
        groups = grouped_by_level[level]
        if (
            max_concurrent_agents is not None
            and max_concurrent_agents > 0
            and len(groups) > max_concurrent_agents
        ):
            waves.extend(
                groups[i : i + max_concurrent_agents]
                for i in range(0, len(groups), max_concurrent_agents)
            )
        else:
            waves.append(groups)

    return waves


def actual_diff_overlaps(files_a: frozenset[str], files_b: frozenset[str]) -> bool:
    """Return True if two groups' actual changed-file sets intersect (REQ-013).

    Checked against the real diff at merge-queue time, not just declared
    paths — any intersection is treated as a merge-conflict-equivalent hard
    stop, even when git itself would not flag a textual conflict.
    """
    return bool(files_a & files_b)


def dependency_wait_satisfied(dependency_group_states: Iterable[str]) -> bool:
    """Return True only when EVERY dependency of a `Sequential` group has
    reached the exact `Merged` state (REQ-012). Every other state — including
    `AwaitingMerge` or `ConflictHalted` — keeps the dependent group waiting.

    Takes every dependency's state, not one: a group can gate on more than one
    other group, and checking a single dependency would dispatch it off a tip
    the remaining dependencies' work has not landed on. A group with no
    dependencies passes vacuously; callers gate on the label, not on this.
    """
    if isinstance(dependency_group_states, str):
        raise TypeError(
            "dependency_wait_satisfied takes one state per dependency, not a single "
            f"state string: pass [{dependency_group_states!r}], not {dependency_group_states!r}. "
            "A bare string is a valid Iterable[str] that iterates characters, so this "
            "would otherwise answer False without anything catching it."
        )
    return all(state == MERGED_STATE for state in dependency_group_states)


def attribute_failure(
    failing_files: frozenset[str],
    group_file_sets: dict[str, frozenset[str]],
) -> str | None:
    """Attribute a post-merge `make verify` failure to its owning group (REQ-009).

    Assumes each not-yet-merged group's file set was already proven disjoint
    from every other group's (REQ-013), so a failing file belongs to at most
    one group. Returns that group's ID only when `failing_files` is fully
    contained in that one group's file set — a full-containment check, not
    a mere intersection. Returns None when the failure spans files from 2+
    groups, or when it intersects exactly one group's files but also
    includes a file no group owns (a partial match), meaning: escalate to
    the human instead of routing the fix to a single group.
    """
    owning_groups = {
        group_id for group_id, files in group_file_sets.items() if failing_files & files
    }
    if len(owning_groups) != 1:
        return None
    group_id = next(iter(owning_groups))
    if not failing_files.issubset(group_file_sets[group_id]):
        return None
    return group_id


def should_halt_worktree_creation(exit_code: int, timed_out: bool) -> bool:
    """Return True on any non-zero exit code or timeout from worktree setup
    (REQ-010) — a `git worktree add` failure or a `uv sync`/`npm ci` project-
    setup step that failed or timed out. A True result halts further
    worktree creation and requires an explicit human choice between serial
    fallback and retry; it never triggers a silent shared-checkout fallback.
    """
    return exit_code != 0 or timed_out


def _sequential_label(dependency_group_ids: frozenset[str]) -> str:
    return f"Sequential (must follow {', '.join(sorted(dependency_group_ids))})"


def parse_sequential_label(label: str) -> tuple[str, ...]:
    """Return every group ID a `Sequential (must follow ...)` label names.

    A group can genuinely gate on more than one other group, so the label
    carries a comma-separated list and this is the one place that reads it —
    the waves calculation, the advisory-label path, and any caller parsing a
    plan's own text all come through here rather than repeating the pattern.
    """
    match = re.search(r"Sequential \(must follow ([^)]+)\)", label)
    if match is None:
        return ()
    return tuple(
        sorted({part.strip() for part in match.group(1).split(",") if part.strip()})
    )


def _find_dependency_cycle(
    dependency: dict[str, frozenset[str]],
) -> list[str] | None:
    """Return the group IDs forming a cycle in `dependency`, if any, else None.

    `dependency` maps a follower group to every leader group it must wait on,
    so a group has as many outgoing edges as it has dependencies. A depth-first
    walk over those edges reports the first back-edge it reaches, and the
    returned list is that cycle in walk order.
    """
    on_path: dict[str, int] = {}
    path: list[str] = []
    finished: set[str] = set()

    def walk(group_id: str) -> list[str] | None:
        if group_id in finished:
            return None
        if group_id in on_path:
            return path[on_path[group_id] :]
        on_path[group_id] = len(path)
        path.append(group_id)
        for leader in sorted(dependency.get(group_id, frozenset())):
            cycle = walk(leader)
            if cycle is not None:
                return cycle
        path.pop()
        del on_path[group_id]
        finished.add(group_id)
        return None

    for start in sorted(dependency):
        cycle = walk(start)
        if cycle is not None:
            return cycle
    return None
