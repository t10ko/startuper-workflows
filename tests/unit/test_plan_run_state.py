from __future__ import annotations

from pathlib import Path

import pytest

from agentic_workflows.plan_run_state import (
    LEGACY_RUN_STATE_PATH,
    PLAN_RUNS_DIR,
    PlanRunState,
    parse_plan_run_state,
    record_path_for_branch,
    update_plan_run_state,
    write_plan_run_state,
)


def _sample_state(narrative: str = "") -> PlanRunState:
    return PlanRunState(
        status="InProgress",
        branch="plan/foo-bar",
        integration_worktree="/tmp/integration/foo-bar",
        verify_status_sha="a1b2c3d4",
        secret_scan_clean_sha="e5f6a7b8",  # noqa: S106
        pr_url="https://github.com/example/repo/pull/1",
        terminal_outcome="",
        narrative=narrative,
    )


def _header_block(status: str = "InProgress") -> str:
    return "\n".join(
        [
            f"Run status: {status}",
            "Branch: plan/foo-bar",
            "Integration worktree: /tmp/integration/foo-bar",
            "Verify-status SHA: a1b2c3d4",
            "Secret-scan-clean SHA: e5f6a7b8",
            "PR URL: https://github.com/example/repo/pull/1",
            "Terminal outcome: ",
        ]
    )


# --- record_path_for_branch ---------------------------------------------


def test_record_path_for_branch_replaces_every_slash_under_default_dir() -> None:
    result = record_path_for_branch("plan/foo/bar")

    assert result == PLAN_RUNS_DIR / "plan-foo-bar.md"


def test_record_path_for_branch_no_slash_used_as_is() -> None:
    result = record_path_for_branch("standalone-branch")

    assert result == PLAN_RUNS_DIR / "standalone-branch.md"


def test_record_path_for_branch_honors_explicit_base_dir(tmp_path: Path) -> None:
    result = record_path_for_branch("plan/foo-bar", base_dir=tmp_path)

    assert result == tmp_path / "plan-foo-bar.md"


# --- parse_plan_run_state: round trip -----------------------------------


def test_parse_plan_run_state_round_trips_with_narrative() -> None:
    narrative = "First narrative line.\nSecond narrative line."
    text = _header_block() + "\n" + narrative

    parsed = parse_plan_run_state(text)

    assert parsed == _sample_state(narrative=narrative)


def test_parse_plan_run_state_round_trips_with_empty_narrative() -> None:
    text = _header_block()

    parsed = parse_plan_run_state(text)

    assert parsed == _sample_state(narrative="")


# --- parse_plan_run_state: fail-closed cases ----------------------------


def test_parse_plan_run_state_returns_none_for_too_few_lines() -> None:
    text = "Run status: InProgress\nBranch: plan/foo-bar"

    assert parse_plan_run_state(text) is None


def test_parse_plan_run_state_returns_none_for_fields_out_of_order() -> None:
    lines = _header_block().split("\n")
    lines[0], lines[1] = lines[1], lines[0]
    text = "\n".join(lines)

    assert parse_plan_run_state(text) is None


def test_parse_plan_run_state_returns_none_for_typo_in_label() -> None:
    text = _header_block().replace("Branch:", "Brnach:")

    assert parse_plan_run_state(text) is None


@pytest.mark.parametrize("bad_status", ["Complete", "", "banana"])
def test_parse_plan_run_state_returns_none_for_invalid_status(
    bad_status: str,
) -> None:
    text = _header_block(status=bad_status)

    assert parse_plan_run_state(text) is None


def test_parse_plan_run_state_accepts_bare_label_with_no_trailing_space() -> None:
    # A header line with no value at all ("Label:", no trailing space) is a
    # distinct accepted form from "Label: " (trailing space, empty value) —
    # exercise it explicitly rather than only ever hitting the latter.
    lines = _header_block().split("\n")
    lines[5] = "PR URL:"
    text = "\n".join(lines)

    parsed = parse_plan_run_state(text)

    assert parsed is not None
    assert parsed.pr_url == ""


# --- write_plan_run_state + parse round trip via tmp_path ----------------


def test_write_then_parse_round_trip_with_narrative(tmp_path: Path) -> None:
    state = _sample_state(narrative="Some narrative.\nMore narrative.")
    path = tmp_path / "run.md"

    write_plan_run_state(path, state)
    parsed = parse_plan_run_state(path.read_text(encoding="utf-8"))

    assert parsed == state


def test_write_then_parse_round_trip_with_empty_narrative(tmp_path: Path) -> None:
    state = _sample_state(narrative="")
    path = tmp_path / "run.md"

    write_plan_run_state(path, state)
    parsed = parse_plan_run_state(path.read_text(encoding="utf-8"))

    assert parsed == state


def test_write_then_parse_round_trip_preserves_non_newline_whitespace(
    tmp_path: Path,
) -> None:
    # '\x0b' (vertical tab) is a line boundary for str.splitlines() but not
    # one the writer ever produces (it only ever joins/splits on '\n').
    # Parsing must not silently collapse it into '\n'.
    state = _sample_state(narrative="line one\x0bstill line one")
    path = tmp_path / "run.md"

    write_plan_run_state(path, state)
    parsed = parse_plan_run_state(path.read_text(encoding="utf-8"))

    assert parsed == state


# --- update_plan_run_state ------------------------------------------------


def test_update_plan_run_state_changes_only_named_field(tmp_path: Path) -> None:
    state = _sample_state(narrative="Untouched narrative.")
    path = tmp_path / "run.md"
    write_plan_run_state(path, state)

    updated = update_plan_run_state(path, verify_status_sha="newsha123")

    expected = PlanRunState(
        status=state.status,
        branch=state.branch,
        integration_worktree=state.integration_worktree,
        verify_status_sha="newsha123",
        secret_scan_clean_sha=state.secret_scan_clean_sha,
        pr_url=state.pr_url,
        terminal_outcome=state.terminal_outcome,
        narrative=state.narrative,
    )
    assert updated == expected
    assert parse_plan_run_state(path.read_text(encoding="utf-8")) == expected


def test_update_plan_run_state_can_change_two_fields_at_once(
    tmp_path: Path,
) -> None:
    state = _sample_state(narrative="Untouched narrative.")
    path = tmp_path / "run.md"
    write_plan_run_state(path, state)

    updated = update_plan_run_state(
        path,
        secret_scan_clean_sha="cleansha456",  # noqa: S106
        pr_url="https://github.com/example/repo/pull/2",
    )

    expected = PlanRunState(
        status=state.status,
        branch=state.branch,
        integration_worktree=state.integration_worktree,
        verify_status_sha=state.verify_status_sha,
        secret_scan_clean_sha="cleansha456",  # noqa: S106
        pr_url="https://github.com/example/repo/pull/2",
        terminal_outcome=state.terminal_outcome,
        narrative=state.narrative,
    )
    assert updated == expected
    assert parse_plan_run_state(path.read_text(encoding="utf-8")) == expected


def test_update_plan_run_state_raises_value_error_on_unparsable_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "garbage.md"
    path.write_text("this is not a valid plan run state file", encoding="utf-8")

    with pytest.raises(ValueError, match=str(path)):
        update_plan_run_state(path, verify_status_sha="whatever")


# --- legacy path regression -----------------------------------------------


def test_legacy_run_state_path_matches_known_literal() -> None:
    assert Path("docs/runs/parallel-run-state.md") == LEGACY_RUN_STATE_PATH
