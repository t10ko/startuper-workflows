import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / ".agents"
    / "scripts"
    / "parallel_plan_grouping.py"
)


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "parallel_plan_grouping",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_label_groups_disjoint_files_are_independent() -> None:
    module = _load_module()
    tasks = [
        module.Task(
            task_id="1",
            group_id="A",
            files=frozenset({"src/a.py"}),
            consumes=frozenset(),
            produces=frozenset(),
            advisory_label=None,
        ),
        module.Task(
            task_id="2",
            group_id="B",
            files=frozenset({"src/b.py"}),
            consumes=frozenset(),
            produces=frozenset(),
            advisory_label=None,
        ),
    ]

    labels = module.label_groups(tasks)

    assert labels == {
        "A": "Independent (parallel-safe)",
        "B": "Independent (parallel-safe)",
    }


def test_label_groups_shared_file_path_forces_sequential() -> None:
    module = _load_module()
    tasks = [
        module.Task(
            task_id="1",
            group_id="A",
            files=frozenset({"src/shared.py"}),
            consumes=frozenset(),
            produces=frozenset(),
            advisory_label="Independent (parallel-safe)",
        ),
        module.Task(
            task_id="2",
            group_id="B",
            files=frozenset({"src/shared.py"}),
            consumes=frozenset(),
            produces=frozenset(),
            advisory_label="Independent (parallel-safe)",
        ),
    ]

    labels = module.label_groups(tasks)

    # Shared file overlap wins even though the task-spec advisory label
    # (for both groups) claimed Independent — REQ-002/AC-003.
    assert labels["B"] == "Sequential (must follow A)"
    assert labels["A"] == "Independent (parallel-safe)"


def test_label_groups_disjoint_paths_but_consumes_produces_overlap_forces_sequential() -> (
    None
):
    module = _load_module()
    tasks = [
        module.Task(
            task_id="1",
            group_id="A",
            files=frozenset({"src/a.py"}),
            consumes=frozenset(),
            produces=frozenset({"build_thing()"}),
            advisory_label=None,
        ),
        module.Task(
            task_id="2",
            group_id="B",
            files=frozenset({"src/b.py"}),
            consumes=frozenset({"build_thing()"}),
            produces=frozenset(),
            advisory_label=None,
        ),
    ]

    labels = module.label_groups(tasks)

    assert labels["A"] == "Independent (parallel-safe)"
    assert labels["B"] == "Sequential (must follow A)"


def test_label_groups_never_upgrades_advisory_sequential_to_independent() -> None:
    module = _load_module()
    tasks = [
        module.Task(
            task_id="1",
            group_id="A",
            files=frozenset({"src/a.py"}),
            consumes=frozenset(),
            produces=frozenset(),
            advisory_label=None,
        ),
        module.Task(
            task_id="2",
            group_id="B",
            files=frozenset({"src/b.py"}),
            consumes=frozenset(),
            produces=frozenset(),
            advisory_label="Sequential (must follow A)",
        ),
    ]

    labels = module.label_groups(tasks)

    # No file or Consumes/Produces collision was found on re-validation, but
    # the task-spec's advisory Sequential label must still never be upgraded
    # to Independent (REQ-003).
    assert labels["B"] == "Sequential (must follow A)"
    assert labels["A"] == "Independent (parallel-safe)"


def test_label_groups_mutual_consumes_produces_cycle_raises() -> None:
    module = _load_module()
    tasks = [
        module.Task(
            task_id="1",
            group_id="A",
            files=frozenset({"src/a.py"}),
            consumes=frozenset({"produce_b()"}),
            produces=frozenset({"produce_a()"}),
            advisory_label=None,
        ),
        module.Task(
            task_id="2",
            group_id="B",
            files=frozenset({"src/b.py"}),
            consumes=frozenset({"produce_a()"}),
            produces=frozenset({"produce_b()"}),
            advisory_label=None,
        ),
    ]

    # A consumes what B produces and B consumes what A produces: a circular
    # Sequential dependency that would make dependency_wait_satisfied() poll
    # forever, since neither group could ever reach Merged first. This must
    # surface as an explicit error naming both groups, not a silent label.
    with pytest.raises(ValueError, match="A") as exc_info:
        module.label_groups(tasks)
    assert "B" in str(exc_info.value)


def test_actual_diff_overlaps_is_hard_stop_despite_disjoint_declared_paths() -> None:
    module = _load_module()

    declared_a = frozenset({"src/a.py"})
    declared_b = frozenset({"src/b.py"})
    assert module.actual_diff_overlaps(declared_a, declared_b) is False

    actual_a = frozenset({"src/a.py", "src/shared_helper.py"})
    actual_b = frozenset({"src/b.py", "src/shared_helper.py"})
    assert module.actual_diff_overlaps(actual_a, actual_b) is True


def test_dependency_wait_satisfied_blocks_on_any_state_other_than_merged() -> None:
    module = _load_module()

    assert module.dependency_wait_satisfied(["Merged"]) is True
    assert module.dependency_wait_satisfied(["AwaitingMerge"]) is False
    assert module.dependency_wait_satisfied(["ConflictHalted"]) is False
    assert module.dependency_wait_satisfied(["InProgress"]) is False


def test_dependency_wait_rejects_a_bare_string_of_one_state() -> None:
    module = _load_module()

    with pytest.raises(TypeError, match="one state per dependency"):
        module.dependency_wait_satisfied("Merged")


def test_attribute_failure_returns_none_when_files_span_two_groups() -> None:
    module = _load_module()
    group_file_sets = {
        "A": frozenset({"src/a.py"}),
        "B": frozenset({"src/b.py"}),
    }

    single_group_failure = frozenset({"src/a.py"})
    assert module.attribute_failure(single_group_failure, group_file_sets) == "A"

    cross_group_failure = frozenset({"src/a.py", "src/b.py"})
    assert module.attribute_failure(cross_group_failure, group_file_sets) is None


def test_attribute_failure_returns_none_when_failing_file_owned_by_no_group() -> None:
    module = _load_module()
    group_file_sets = {
        "A": frozenset({"src/a.py"}),
        "B": frozenset({"src/b.py"}),
    }

    # One file inside group A's set, one file that belongs to no group at
    # all. This intersects exactly one group (A), but failing_files is not
    # a subset of A's files, so it must escalate rather than being
    # attributed to A's partial match.
    partial_match_failure = frozenset({"src/a.py", "src/unowned.py"})
    assert module.attribute_failure(partial_match_failure, group_file_sets) is None


def test_should_halt_worktree_creation_on_nonzero_exit_or_timeout() -> None:
    module = _load_module()

    assert module.should_halt_worktree_creation(exit_code=0, timed_out=False) is False
    assert module.should_halt_worktree_creation(exit_code=1, timed_out=False) is True
    assert module.should_halt_worktree_creation(exit_code=0, timed_out=True) is True


def test_calculate_critical_path_finds_longest_sequential_chain() -> None:
    module = _load_module()
    tasks = [
        module.Task(
            task_id="1",
            group_id="A",
            files=frozenset({"src/a.py"}),
            consumes=frozenset(),
            produces=frozenset({"contract_a"}),
            advisory_label=None,
        ),
        module.Task(
            task_id="2",
            group_id="B",
            files=frozenset({"src/b.py"}),
            consumes=frozenset(),
            produces=frozenset({"contract_b"}),
            advisory_label=None,
        ),
        module.Task(
            task_id="3",
            group_id="C",
            files=frozenset({"src/c.py"}),
            consumes=frozenset({"contract_a"}),
            produces=frozenset({"contract_c"}),
            advisory_label=None,
        ),
        module.Task(
            task_id="4",
            group_id="D",
            files=frozenset({"src/d.py"}),
            consumes=frozenset({"contract_c"}),
            produces=frozenset({"contract_d"}),
            advisory_label=None,
        ),
    ]

    critical_path = module.calculate_critical_path(tasks)
    assert critical_path == ["A", "C", "D"]


def test_calculate_execution_waves_batches_by_concurrency_cap() -> None:
    module = _load_module()
    labels = {
        "A": "Independent (parallel-safe)",
        "B": "Independent (parallel-safe)",
        "C": "Independent (parallel-safe)",
        "D": "Independent (parallel-safe)",
        "E": "Independent (parallel-safe)",
        "F": "Independent (parallel-safe)",
        "G": "Sequential (must follow A)",
    }
    waves = module.calculate_execution_waves(labels, max_concurrent_agents=5)
    # Wave 1 has 6 independent groups; capped at 5 per batch -> batch 1 has 5, batch 2 has 1
    assert len(waves) >= 3
    assert waves[0] == ["A", "B", "C", "D", "E"]
    assert waves[1] == ["F"]
    assert waves[2] == ["G"]


def test_calculate_execution_waves_handles_wave_0_bootstrap() -> None:
    module = _load_module()
    labels = {
        "0_config": "Independent (parallel-safe)",
        "A": "Sequential (must follow 0_config)",
        "B": "Sequential (must follow 0_config)",
    }
    waves = module.calculate_execution_waves(labels, max_concurrent_agents=5)
    assert waves[0] == ["0_config"]
    assert waves[1] == ["A", "B"]


def _task(
    module: ModuleType,
    task_id: str,
    group_id: str,
    files: frozenset[str] = frozenset(),
    consumes: frozenset[str] = frozenset(),
    produces: frozenset[str] = frozenset(),
) -> object:
    return module.Task(
        task_id=task_id,
        group_id=group_id,
        files=files or frozenset({f"src/t{task_id}.py"}),
        consumes=consumes,
        produces=produces,
        advisory_label=None,
    )


def test_review_schedule_is_gone() -> None:
    module = _load_module()

    assert not hasattr(module, "review_schedule")
    assert not hasattr(module, "GroupReviewPlan")


def test_label_names_every_group_a_group_must_follow() -> None:
    module = _load_module()
    tasks = [
        _task(module, "1", "A", produces=frozenset({"contract_a"})),
        _task(module, "2", "B", produces=frozenset({"contract_b"})),
        _task(
            module,
            "3",
            "C",
            consumes=frozenset({"contract_a", "contract_b"}),
        ),
    ]

    labels = module.label_groups(tasks)

    assert labels["A"] == module.INDEPENDENT_LABEL
    assert labels["B"] == module.INDEPENDENT_LABEL
    assert labels["C"] == "Sequential (must follow A, B)"


def test_a_group_waits_until_every_dependency_is_merged() -> None:
    module = _load_module()

    assert module.dependency_wait_satisfied(["Merged", "Merged"]) is True
    assert module.dependency_wait_satisfied(["Merged", "AwaitingMerge"]) is False
    assert module.dependency_wait_satisfied(["InProgress"]) is False
    assert module.dependency_wait_satisfied([]) is True


def test_an_advisory_label_naming_several_groups_is_parsed_as_several() -> None:
    module = _load_module()
    tasks = [
        module.Task(
            task_id="1",
            group_id="A",
            files=frozenset({"src/a.py"}),
            consumes=frozenset(),
            produces=frozenset(),
            advisory_label=None,
        ),
        module.Task(
            task_id="2",
            group_id="B",
            files=frozenset({"src/b.py"}),
            consumes=frozenset(),
            produces=frozenset(),
            advisory_label=None,
        ),
        module.Task(
            task_id="3",
            group_id="C",
            files=frozenset({"src/c.py"}),
            consumes=frozenset(),
            produces=frozenset(),
            advisory_label="Sequential (must follow A, B)",
        ),
    ]

    labels = module.label_groups(tasks)

    assert labels["C"] == "Sequential (must follow A, B)"


def test_a_cycle_through_a_second_dependency_still_raises() -> None:
    module = _load_module()
    tasks = [
        _task(
            module,
            "1",
            "A",
            consumes=frozenset({"contract_c"}),
            produces=frozenset({"contract_a"}),
        ),
        _task(module, "2", "B", produces=frozenset({"contract_b"})),
        _task(
            module,
            "3",
            "C",
            consumes=frozenset({"contract_a", "contract_b"}),
            produces=frozenset({"contract_c"}),
        ),
    ]

    with pytest.raises(ValueError, match="Circular"):
        module.label_groups(tasks)


def test_execution_waves_place_a_group_after_all_of_its_dependencies() -> None:
    module = _load_module()
    labels = {
        "A": "Independent (parallel-safe)",
        "B": "Sequential (must follow A)",
        "C": "Sequential (must follow A, B)",
    }

    waves = module.calculate_execution_waves(labels, max_concurrent_agents=5)

    assert waves == [["A"], ["B"], ["C"]]


def test_critical_path_follows_the_deepest_dependency() -> None:
    module = _load_module()
    tasks = [
        _task(module, "1", "A", produces=frozenset({"contract_a"})),
        _task(
            module,
            "2",
            "B",
            consumes=frozenset({"contract_a"}),
            produces=frozenset({"contract_b"}),
        ),
        _task(
            module,
            "3",
            "C",
            consumes=frozenset({"contract_a", "contract_b"}),
        ),
    ]

    assert module.calculate_critical_path(tasks) == ["A", "B", "C"]


def test_a_file_edited_by_two_groups_is_reported_with_both_groups() -> None:
    """One file in two groups is what forces one of them to wait.

    Measured 2026-09-21 on `docs/plans/2026-09-20-llm-stall-timeout-streaming
    -transport.md`: six files were edited from two or three groups each, and
    `src/llm/client/unified_client.py` alone chained groups 1, 2 and 5 into a
    sequence that could not run concurrently.
    """
    module = _load_module()
    tasks = [
        _task(module, "1", "A", files=frozenset({"src/shared.py"})),
        _task(module, "2", "B", files=frozenset({"src/shared.py", "src/only_b.py"})),
    ]

    assert module.files_shared_across_groups(tasks) == {"src/shared.py": ["A", "B"]}


def test_a_file_edited_twice_inside_one_group_is_not_a_finding() -> None:
    """Tasks in one group already run in sequence in one checkout.

    Sharing a file there costs nothing: the group is precisely the set of
    tasks that share files, and that is the design working.
    """
    module = _load_module()
    tasks = [
        _task(module, "1", "A", files=frozenset({"src/shared.py"})),
        _task(module, "2", "A", files=frozenset({"src/shared.py"})),
    ]

    assert module.files_shared_across_groups(tasks) == {}


def test_a_file_reaching_three_groups_names_all_three() -> None:
    """The count of groups a file chains is the size of the wait it forces."""
    module = _load_module()
    tasks = [
        _task(module, "1", "A", files=frozenset({"src/hot.py"})),
        _task(module, "2", "B", files=frozenset({"src/hot.py"})),
        _task(module, "3", "C", files=frozenset({"src/hot.py"})),
    ]

    assert module.files_shared_across_groups(tasks) == {"src/hot.py": ["A", "B", "C"]}


def test_fully_disjoint_groups_report_nothing() -> None:
    module = _load_module()
    tasks = [
        _task(module, "1", "A", files=frozenset({"src/a.py"})),
        _task(module, "2", "B", files=frozenset({"src/b.py"})),
    ]

    assert module.files_shared_across_groups(tasks) == {}
