"""The lease/ledger payload contract and the fail-closed config loader.

The dataclasses were pydantic models in the origin repo; the standalone port
replaces them with frozen dataclasses whose `__post_init__`/`from_payload`
raise plain `ValueError` — so every "tampered payload is rejected at load"
behavior below pins the `ValueError` (or its `WorktreeCapacityError`
subclass, which also is one) directly.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from agentic_workflows.worktree_capacity import (
    CONFIG_PATH,
    LOCAL_CONFIG_PATH,
    WorktreeCapacityError,
    WorktreeLease,
    WorktreeLeaseLedger,
    load_leases,
    load_max_concurrent_worktrees,
    resolve_config_path,
    store_leases,
)


def _lease(worktree: Path, run_id: str = "plan/foo") -> WorktreeLease:
    return WorktreeLease(
        worktree=worktree,
        run_id=run_id,
        holder_pid=4242,
        holder_host="some-host",
        acquired_at=datetime.datetime(2026, 9, 23, 12, 0, 0, tzinfo=datetime.UTC),
    )


# --- round trip -----------------------------------------------------------


def test_a_lease_round_trips_through_its_json_payload(tmp_path: Path):
    lease = _lease(tmp_path / "wt")

    restored = WorktreeLease.from_payload(json.loads(json.dumps(lease.to_dict())))

    assert restored == lease


def test_a_ledger_round_trips_through_its_json_payload(tmp_path: Path):
    ledger = WorktreeLeaseLedger(
        leases={
            (tmp_path / "wt-a").resolve().as_posix(): _lease(tmp_path / "wt-a"),
            (tmp_path / "wt-b").resolve().as_posix(): _lease(
                tmp_path / "wt-b", run_id="plan/bar"
            ),
        }
    )

    restored = WorktreeLeaseLedger.from_payload(json.loads(json.dumps(ledger.to_dict())))

    assert restored == ledger


def test_store_then_load_round_trips_the_ledger(tmp_path: Path):
    path = tmp_path / "ledgers" / "leases.json"
    ledger = WorktreeLeaseLedger(
        leases={(tmp_path / "wt").resolve().as_posix(): _lease(tmp_path / "wt")}
    )

    store_leases(path, ledger)

    assert load_leases(path) == ledger


def test_an_absent_ledger_loads_as_empty(tmp_path: Path):
    assert load_leases(tmp_path / "never-written.json") == WorktreeLeaseLedger()


# --- key identity ----------------------------------------------------------


def test_a_ledger_key_must_be_the_lease_worktree_in_resolved_posix_form(tmp_path: Path):
    lease = _lease(tmp_path / "wt")
    resolved = lease.worktree.resolve().as_posix()

    with pytest.raises(ValueError, match="resolved posix form"):
        WorktreeLeaseLedger(leases={f"{resolved}-tampered": lease})


def test_a_tampered_ledger_file_fails_closed_at_load(tmp_path: Path):
    path = tmp_path / "leases.json"
    lease = _lease(tmp_path / "wt")
    payload = {"leases": {"/some/other/key": lease.to_dict()}}
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(WorktreeCapacityError, match="unreadable or unparsable"):
        load_leases(path)


def test_an_unparsable_ledger_file_fails_closed_at_load(tmp_path: Path):
    path = tmp_path / "leases.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(WorktreeCapacityError, match="unreadable or unparsable"):
        load_leases(path)


# --- lease field validation ------------------------------------------------


def test_a_naive_acquired_at_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        WorktreeLease(
            worktree=Path("/tmp/wt"),
            run_id="plan/foo",
            holder_pid=1,
            holder_host="h",
            acquired_at=datetime.datetime(2026, 9, 23, 12, 0, 0),
        )


def test_a_naive_acquired_at_surviving_in_json_is_rejected_at_load():
    payload = _lease(Path("/tmp/wt")).to_dict()
    payload["acquired_at"] = "2026-09-23T12:00:00"  # no offset

    with pytest.raises(ValueError, match="timezone-aware"):
        WorktreeLease.from_payload(payload)


@pytest.mark.parametrize("pid", [0, -1])
def test_a_holder_pid_below_one_is_rejected(pid: int):
    with pytest.raises(ValueError, match="holder_pid"):
        WorktreeLease(
            worktree=Path("/tmp/wt"),
            run_id="plan/foo",
            holder_pid=pid,
            holder_host="h",
            acquired_at=datetime.datetime.now(datetime.UTC),
        )


def test_a_boolean_holder_pid_is_rejected():
    with pytest.raises(ValueError, match="holder_pid"):
        WorktreeLease(
            worktree=Path("/tmp/wt"),
            run_id="plan/foo",
            holder_pid=True,
            holder_host="h",
            acquired_at=datetime.datetime.now(datetime.UTC),
        )


def test_unknown_lease_fields_are_rejected():
    payload = _lease(Path("/tmp/wt")).to_dict()
    payload["renewed_at"] = payload["acquired_at"]

    with pytest.raises(ValueError, match="unknown lease fields"):
        WorktreeLease.from_payload(payload)


def test_unknown_ledger_fields_are_rejected():
    payload = {"leases": {}, "max_concurrent": 5}

    with pytest.raises(ValueError, match="unknown lease-ledger fields"):
        WorktreeLeaseLedger.from_payload(payload)


def test_a_ledger_payload_that_is_not_an_object_is_rejected():
    with pytest.raises(ValueError, match="must be a JSON object"):
        WorktreeLeaseLedger.from_payload([_lease(Path("/tmp/wt")).to_dict()])


# --- fail-closed config loading --------------------------------------------


def test_a_missing_config_file_names_its_path_and_refuses_a_default(tmp_path: Path):
    missing = tmp_path / "config.toml"

    with pytest.raises(WorktreeCapacityError, match=missing.name) as exc_info:
        load_max_concurrent_worktrees(missing)

    assert "does not exist" in str(exc_info.value)
    assert "no default is applied" in str(exc_info.value)


def test_an_unparsable_config_file_raises(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("[worktrees\nmax_concurrent = ", encoding="utf-8")

    with pytest.raises(WorktreeCapacityError, match="cannot read the worktree cap"):
        load_max_concurrent_worktrees(path)


def test_a_config_without_the_worktrees_table_raises(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("max_concurrent = 5\n", encoding="utf-8")

    with pytest.raises(WorktreeCapacityError, match="has no \\[worktrees\\] table"):
        load_max_concurrent_worktrees(path)


@pytest.mark.parametrize(
    "content",
    [
        # Table without the key.
        "[worktrees]\nother_key = 5\n",
        # Non-integer values.
        '[worktrees]\nmax_concurrent = "5"\n',
        "[worktrees]\nmax_concurrent = 5.5\n",
        # A bool is an int subtype; it must not slip through.
        "[worktrees]\nmax_concurrent = true\n",
    ],
)
def test_a_non_integer_cap_raises(tmp_path: Path, content: str):
    path = tmp_path / "config.toml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(WorktreeCapacityError, match="must be a whole number"):
        load_max_concurrent_worktrees(path)


@pytest.mark.parametrize("value", [0, -3])
def test_a_non_positive_cap_raises(tmp_path: Path, value: int):
    path = tmp_path / "config.toml"
    path.write_text(f"[worktrees]\nmax_concurrent = {value}\n", encoding="utf-8")

    with pytest.raises(WorktreeCapacityError, match="at least 1"):
        load_max_concurrent_worktrees(path)


def test_a_valid_config_yields_the_cap(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("[worktrees]\nmax_concurrent = 5\n", encoding="utf-8")

    assert load_max_concurrent_worktrees(path) == 5


def test_the_canonical_config_path_is_the_agents_toml():
    assert CONFIG_PATH == Path(".agents/config.toml")


def test_resolve_config_path_prefers_the_local_override(tmp_path: Path):
    (tmp_path / CONFIG_PATH).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / CONFIG_PATH).write_text(
        "[worktrees]\nmax_concurrent = 5\n", encoding="utf-8"
    )
    (tmp_path / LOCAL_CONFIG_PATH).write_text(
        "[worktrees]\nmax_concurrent = 2\n", encoding="utf-8"
    )

    assert resolve_config_path(tmp_path) == tmp_path / LOCAL_CONFIG_PATH
    assert load_max_concurrent_worktrees(resolve_config_path(tmp_path)) == 2


def test_resolve_config_path_falls_back_to_the_canonical_file(tmp_path: Path):
    (tmp_path / CONFIG_PATH).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / CONFIG_PATH).write_text(
        "[worktrees]\nmax_concurrent = 5\n", encoding="utf-8"
    )

    assert resolve_config_path(tmp_path) == tmp_path / CONFIG_PATH
