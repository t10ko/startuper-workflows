import subprocess
from pathlib import Path

import pytest

from agentic_workflows.git_write_guard import (
    build_git_danger_block_message,
    is_git_dangerous_command,
)
from agentic_workflows.plan_run_state import (
    PlanRunState,
    RunStatus,
    record_path_for_branch,
    write_plan_run_state,
)


def _worktree_with_main(tmp_path: Path) -> tuple[Path, Path]:
    """A main-checkout/linked-worktree pair sharing one gitdir link. Push
    authorization tests need both: the plan-run record is written into the
    main checkout while the push command runs from the worktree."""
    main_repo = tmp_path / "main-repo"
    (main_repo / ".git").mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text(
        f"gitdir: {main_repo}/.git/worktrees/agent-1\n", encoding="utf-8"
    )
    return main_repo, worktree


def _any_sha_resolves(_location: Path, _sha: str) -> bool:
    """The injected `sha_resolves` seam for tests that exercise facts OTHER
    than recorded-SHA resolution: this fake pair of directories is not a real
    repository, so without the seam the real `git cat-file` subprocess would
    deny every record here for a fact these tests are not about."""
    return True


def _write_record(
    main_repo: Path,
    *,
    path_branch: str,
    record_branch: str,
    verify_sha: str,
    clean_sha: str,
    status: RunStatus = "InProgress",
) -> None:
    """Write a plan-run state record into `main_repo`. `path_branch` drives
    the on-disk filename; `record_branch` is the Branch field inside — the two
    differ only in the ownership-mismatch test. `status` is InProgress for
    every test but the finished-run one: only a live run authorizes a push."""
    record_path = main_repo / record_path_for_branch(path_branch)
    write_plan_run_state(
        record_path,
        PlanRunState(
            status=status,
            branch=record_branch,
            integration_worktree="",
            verify_status_sha=verify_sha,
            secret_scan_clean_sha=clean_sha,
            pr_url="",
            terminal_outcome="",
        ),
    )


# --- push authorization: non-canonical forms are always denied -----------


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push origin main",
        "git push --all",
        "git push --mirror",
        "git push origin :refs/heads/main",
        "git push origin feature:main",
        # Right shape, but the destination branch is the protected default.
        "git push -u origin HEAD:main",
    ],
)
def test_non_canonical_push_forms_denied(command: str):
    # Only `git push -u origin HEAD:<non-default-branch>` can ever be allowed;
    # every other push shape is categorically denied by the shape check alone.
    assert is_git_dangerous_command(command) is True


@pytest.mark.parametrize(
    "command",
    [
        "git push -u origin HEAD:plan/foo --force",
        "git push --force-with-lease -u origin HEAD:plan/foo",
    ],
)
def test_force_flags_denied_even_when_otherwise_canonical(command: str):
    # A force flag lengthens the arg list past the exact three-token canonical
    # shape, so it is rejected without any separate force-flag special-casing.
    assert is_git_dangerous_command(command) is True


# --- push authorization: ownership + SHA comparison ----------------------


def test_push_allowed_when_branch_and_both_shas_match(tmp_path: Path):
    main_repo, worktree = _worktree_with_main(tmp_path)
    _write_record(
        main_repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha="deadbeef",
        clean_sha="deadbeef",
    )
    result = is_git_dangerous_command(
        "git push -u origin HEAD:plan/foo",
        worktree,
        rev_parse_head=lambda _cwd: "deadbeef",
        sha_resolves=_any_sha_resolves,
    )
    assert result is False


def test_push_allowed_with_trailing_stderr_redirect(tmp_path: Path):
    # An otherwise-canonical, fully-authorized push must not be denied just
    # because the agent appended `2>&1` out of its own habit of capturing
    # combined output — that redirect never reaches git's own argv (the
    # shell consumes it before exec), so it must not change whether this
    # push is recognized as the one authorized shape.
    main_repo, worktree = _worktree_with_main(tmp_path)
    _write_record(
        main_repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha="deadbeef",
        clean_sha="deadbeef",
    )
    result = is_git_dangerous_command(
        "git push -u origin HEAD:plan/foo 2>&1",
        worktree,
        rev_parse_head=lambda _cwd: "deadbeef",
        sha_resolves=_any_sha_resolves,
    )
    assert result is False


def test_push_still_denied_when_extra_non_redirect_token_follows(tmp_path: Path):
    # The redirect allowance must not become a general "ignore anything
    # trailing" escape hatch: a real extra argument still lengthens the
    # canonical shape and must still be denied.
    main_repo, worktree = _worktree_with_main(tmp_path)
    _write_record(
        main_repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha="deadbeef",
        clean_sha="deadbeef",
    )
    result = is_git_dangerous_command(
        "git push -u origin HEAD:plan/foo --verbose",
        worktree,
        rev_parse_head=lambda _cwd: "deadbeef",
    )
    assert result is True


def test_push_denied_when_the_run_is_finished(tmp_path: Path):
    # A run's record outlives the run. Once a human has closed it, the record
    # still carries the branch and both SHAs, so every other authorization
    # fact still stands — and the gate used to read exactly those and let the
    # push through. What may land after a run is closed is the run owner's
    # decision, not a leftover record's; a Finished record authorizes nothing.
    main_repo, worktree = _worktree_with_main(tmp_path)
    _write_record(
        main_repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha="deadbeef",
        clean_sha="deadbeef",
        status="Finished",
    )
    result = is_git_dangerous_command(
        "git push -u origin HEAD:plan/foo",
        worktree,
        rev_parse_head=lambda _cwd: "deadbeef",
        sha_resolves=_any_sha_resolves,
    )
    assert result is True


def test_finished_run_denial_names_the_finished_run(tmp_path: Path):
    # INV-1: the denial names THE fact that failed, so a finished run never
    # reads as a missing record or a SHA mismatch.
    main_repo, worktree = _worktree_with_main(tmp_path)
    _write_record(
        main_repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha="deadbeef",
        clean_sha="deadbeef",
        status="Finished",
    )
    message = build_git_danger_block_message(
        "git push -u origin HEAD:plan/foo",
        worktree,
        rev_parse_head=lambda _cwd: "deadbeef",
        sha_resolves=_any_sha_resolves,
    )
    assert (
        message == "push denied: this branch's plan run is finished, so its record no "
        "longer authorizes a push"
    )


def test_push_denied_when_no_record_exists(tmp_path: Path):
    _main_repo, worktree = _worktree_with_main(tmp_path)
    result = is_git_dangerous_command(
        "git push -u origin HEAD:plan/foo",
        worktree,
        rev_parse_head=lambda _cwd: "deadbeef",
    )
    assert result is True


def test_push_denied_when_record_branch_mismatches(tmp_path: Path):
    main_repo, worktree = _worktree_with_main(tmp_path)
    _write_record(
        main_repo,
        path_branch="plan/foo",
        record_branch="plan/other",
        verify_sha="deadbeef",
        clean_sha="deadbeef",
    )
    result = is_git_dangerous_command(
        "git push -u origin HEAD:plan/foo",
        worktree,
        rev_parse_head=lambda _cwd: "deadbeef",
    )
    assert result is True


def test_push_denied_when_head_sha_mismatches_verify_sha(tmp_path: Path):
    main_repo, worktree = _worktree_with_main(tmp_path)
    _write_record(
        main_repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha="verifysha",
        clean_sha="verifysha",
    )
    result = is_git_dangerous_command(
        "git push -u origin HEAD:plan/foo",
        worktree,
        rev_parse_head=lambda _cwd: "differentsha",
        sha_resolves=_any_sha_resolves,
    )
    assert result is True


def test_push_denied_when_head_matches_verify_but_not_clean_sha(tmp_path: Path):
    main_repo, worktree = _worktree_with_main(tmp_path)
    _write_record(
        main_repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha="verifysha",
        clean_sha="cleansha",
    )
    result = is_git_dangerous_command(
        "git push -u origin HEAD:plan/foo",
        worktree,
        rev_parse_head=lambda _cwd: "verifysha",
        sha_resolves=_any_sha_resolves,
    )
    assert result is True


# --- push authorization: -C/--git-dir/--work-tree location-override closure


def _second_worktree(tmp_path: Path, main_repo: Path) -> Path:
    """A second linked worktree of the same `main_repo`, distinct from the one
    `_worktree_with_main` builds. Its `.git` gitdir link resolves back to the
    same main checkout, so its plan-run record lookup succeeds — but its HEAD
    is a different commit than the session cwd's, which is what the
    location-override bypass would exploit."""
    other = tmp_path / "other-worktree"
    other.mkdir()
    (other / ".git").write_text(
        f"gitdir: {main_repo}/.git/worktrees/agent-2\n", encoding="utf-8"
    )
    return other


def test_push_denied_when_dash_c_targets_location_with_unverified_head(
    tmp_path: Path,
):
    # `git -C <other-worktree> push ...` would push <other-worktree>'s HEAD,
    # not the session cwd's. The SHA gate must evaluate the -C target's HEAD:
    # here that HEAD ("evilsha") never passed this round's verify/secret scan,
    # so the push must be denied even though the raw session cwd's HEAD
    # ("verifysha") matches the record. Before the fix this authorized the
    # push by verifying the wrong (raw cwd) location's HEAD.
    main_repo, worktree = _worktree_with_main(tmp_path)
    other = _second_worktree(tmp_path, main_repo)
    _write_record(
        main_repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha="verifysha",
        clean_sha="verifysha",
    )
    command = f"git -C {other} push -u origin HEAD:plan/foo"
    message = build_git_danger_block_message(
        command,
        worktree,
        rev_parse_head=lambda loc: "verifysha" if loc == worktree else "evilsha",
        sha_resolves=_any_sha_resolves,
    )
    assert (
        message
        == "push denied: pushed commit does not match this round's verify-status SHA"
    )


def test_push_sha_gate_evaluates_dash_c_target_not_raw_cwd(tmp_path: Path):
    # Mirror of the block: when the -C target's HEAD DOES match the record, the
    # push is authorized even though the raw session cwd's HEAD would not —
    # proving the gate follows the -C target, not the raw cwd, in both
    # directions (a fix that just made every -C push fail would break here).
    main_repo, worktree = _worktree_with_main(tmp_path)
    other = _second_worktree(tmp_path, main_repo)
    _write_record(
        main_repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha="othersha",
        clean_sha="othersha",
    )
    command = f"git -C {other} push -u origin HEAD:plan/foo"
    result = is_git_dangerous_command(
        command,
        worktree,
        rev_parse_head=lambda loc: "othersha" if loc == other else "cwdsha",
        sha_resolves=_any_sha_resolves,
    )
    assert result is False


@pytest.mark.parametrize("flag", ["-C", "--git-dir", "--work-tree"])
def test_push_sha_bypass_closed_for_all_location_overrides(tmp_path: Path, flag: str):
    # Rule-28 sibling of the commit `-C`/`--git-dir`/`--work-tree` bypass-closure
    # tests: every location-override flag must route the SHA gate through the
    # override target, never the raw session cwd. The seam returns the verified
    # SHA ONLY for the raw cwd, so any override resolving elsewhere yields the
    # unverified "evilsha" and is denied at the verify-status gate.
    main_repo, worktree = _worktree_with_main(tmp_path)
    other = _second_worktree(tmp_path, main_repo)
    _write_record(
        main_repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha="verifysha",
        clean_sha="verifysha",
    )
    target = f"{other}/.git" if flag == "--git-dir" else str(other)
    command = f"git {flag} {target} push -u origin HEAD:plan/foo"
    message = build_git_danger_block_message(
        command,
        worktree,
        rev_parse_head=lambda loc: "verifysha" if loc == worktree else "evilsha",
        sha_resolves=_any_sha_resolves,
    )
    assert (
        message
        == "push denied: pushed commit does not match this round's verify-status SHA"
    )


# --- push authorization: specific block messages -------------------------


def test_build_message_specific_reason_for_push_to_main():
    message = build_git_danger_block_message("git push -u origin HEAD:main")
    assert message == "push denied: cannot push to main"


def test_build_message_specific_reason_for_non_canonical_push():
    message = build_git_danger_block_message("git push origin main")
    assert message is not None
    assert "push denied: not the canonical push form" in message
    assert "Most git operations are allowed" not in message


def test_build_message_specific_reason_for_unrecorded_branch(tmp_path: Path):
    _main_repo, worktree = _worktree_with_main(tmp_path)
    message = build_git_danger_block_message(
        "git push -u origin HEAD:plan/foo",
        worktree,
        rev_parse_head=lambda _cwd: "deadbeef",
    )
    assert message == "push denied: branch not recorded as owned by an active run"


# --- REQ-027: every unestablished record fact denies with its own reason --


def test_push_denied_when_record_cannot_be_parsed(tmp_path: Path):
    # A record that exists but parses no better than garbage is a different
    # fact from a missing record, and must not borrow the missing-record
    # reason it used to share with it.
    main_repo, worktree = _worktree_with_main(tmp_path)
    record_path = main_repo / record_path_for_branch("plan/foo")
    record_path.parent.mkdir(parents=True)
    record_path.write_text("not a plan-run record\n", encoding="utf-8")
    message = build_git_danger_block_message(
        "git push -u origin HEAD:plan/foo",
        worktree,
        rev_parse_head=lambda _cwd: "deadbeef",
    )
    assert (
        message
        == "push denied: the plan-run record for this branch exists but could not be parsed"
    )


def test_push_denied_when_record_is_not_valid_utf8(tmp_path: Path):
    # Undecodable record bytes used to escape the OSError handler, reach the
    # generic ValueError handler, and refuse with the deny-list message — a
    # generic refusal (an INV-1 defect) that also falsely claimed a git rule
    # had been consulted. The record fact must be named instead.
    main_repo, worktree = _worktree_with_main(tmp_path)
    record_path = main_repo / record_path_for_branch("plan/foo")
    record_path.parent.mkdir(parents=True)
    record_path.write_bytes(
        b"Run status: InProgress\n\xff\xfe bytes that are not UTF-8"
    )
    message = build_git_danger_block_message(
        "git push -u origin HEAD:plan/foo",
        worktree,
        rev_parse_head=lambda _cwd: "deadbeef",
    )
    assert (
        message
        == "push denied: the plan-run record for this branch is not valid UTF-8 text"
    )


def test_push_denied_when_record_path_is_a_directory(tmp_path: Path):
    # A directory at the record path — like any OSError that is not a missing
    # file — leaves the gate unable to read the record at all, so it must not
    # assert the negative "branch not recorded as owned by an active run",
    # which is exactly what it could not establish. It denies fail-closed
    # with its own honest reason, naming the OS error class.
    main_repo, worktree = _worktree_with_main(tmp_path)
    record_path = main_repo / record_path_for_branch("plan/foo")
    record_path.mkdir(parents=True)
    message = build_git_danger_block_message(
        "git push -u origin HEAD:plan/foo",
        worktree,
        rev_parse_head=lambda _cwd: "deadbeef",
    )
    assert (
        message == "push denied: the plan-run record for this branch could not be read "
        "(IsADirectoryError)"
    )


def test_push_denied_when_record_path_carries_an_embedded_null(tmp_path: Path):
    # A branch name carrying a NUL yields a NUL-bearing record path whose
    # read_text raises ValueError — outside the handler set that named every
    # other read-time fact, it escaped into the generic ValueError handler and
    # refused with the deny-list message: a read failure presented as a git
    # decision (INV-1), and the same fail-open shape Task 48 closed in the
    # resolution leaf for any caller without the message builder's net.
    _main_repo, worktree = _worktree_with_main(tmp_path)
    command = f"git push -u origin HEAD:plan/f{chr(0)}oo"
    message = build_git_danger_block_message(
        command,
        worktree,
        rev_parse_head=lambda _cwd: "deadbeef",
    )
    assert message == (
        "push denied: the plan-run record for this branch could not be read "
        "(ValueError)"
    )


def test_push_denial_names_the_branch_mismatch(tmp_path: Path):
    main_repo, worktree = _worktree_with_main(tmp_path)
    _write_record(
        main_repo,
        path_branch="plan/foo",
        record_branch="plan/other",
        verify_sha="deadbeef",
        clean_sha="deadbeef",
    )
    message = build_git_danger_block_message(
        "git push -u origin HEAD:plan/foo",
        worktree,
        rev_parse_head=lambda _cwd: "deadbeef",
    )
    assert (
        message
        == "push denied: the plan-run record for this branch names a different branch"
    )


@pytest.mark.parametrize(
    ("empty_field", "expected_message"),
    [
        ("verify_sha", "push denied: this round's record carries no verify-status SHA"),
        (
            "clean_sha",
            "push denied: this round's record carries no secret-scan-clean SHA",
        ),
    ],
)
def test_push_denied_when_a_sha_field_is_empty(
    tmp_path: Path, empty_field: str, expected_message: str
):
    # The parser accepts a bare `Label:` line as an empty value, so a record
    # can parse with a SHA field present but carrying nothing — the fact is
    # "no SHA recorded", not "the pushed commit does not match it".
    main_repo, worktree = _worktree_with_main(tmp_path)
    _write_record(
        main_repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha="" if empty_field == "verify_sha" else "deadbeef",
        clean_sha="" if empty_field == "clean_sha" else "deadbeef",
    )
    message = build_git_danger_block_message(
        "git push -u origin HEAD:plan/foo",
        worktree,
        rev_parse_head=lambda _cwd: "deadbeef",
        sha_resolves=_any_sha_resolves,
    )
    assert message == expected_message


def test_push_denied_when_recorded_verify_sha_resolves_to_no_object(
    tmp_path: Path,
):
    # S-11: a recorded SHA that names no commit in the repository (stale or
    # forged) is an unestablishable fact in its own right and must deny with
    # its own reason, not the ordinary mismatch one.
    main_repo, worktree = _worktree_with_main(tmp_path)
    _write_record(
        main_repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha="f" * 40,
        clean_sha="deadbeef",
    )
    message = build_git_danger_block_message(
        "git push -u origin HEAD:plan/foo",
        worktree,
        rev_parse_head=lambda _cwd: "deadbeef",
        sha_resolves=lambda _location, _sha: False,
    )
    assert (
        message
        == "push denied: this round's verify-status SHA does not resolve to a commit in this repository"
    )


def test_push_denied_when_recorded_clean_sha_resolves_to_no_object(
    tmp_path: Path,
):
    main_repo, worktree = _worktree_with_main(tmp_path)
    _write_record(
        main_repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha="verifysha",
        clean_sha="f" * 40,
    )
    message = build_git_danger_block_message(
        "git push -u origin HEAD:plan/foo",
        worktree,
        rev_parse_head=lambda _cwd: "verifysha",
        sha_resolves=lambda _location, sha: sha == "verifysha",
    )
    assert (
        message
        == "push denied: this round's secret-scan-clean SHA does not resolve to a commit in this repository"
    )


def test_option_shaped_recorded_sha_is_refused_before_any_resolution_attempt(
    tmp_path: Path,
):
    # A recorded value starting with `-` can never be an object id, so the
    # refusal is a property of the recorded fact itself: it must short-circuit
    # even an injected `sha_resolves`, never reaching resolution at all —
    # git's argv included. Removing the prefix check from
    # `_recorded_commit_established` puts "-deadbeef" in `attempted` below
    # and reddens this test.
    attempted: list[str] = []

    def _record_attempts(_location: Path, sha: str) -> bool:
        attempted.append(sha)
        return True

    main_repo, worktree = _worktree_with_main(tmp_path)
    _write_record(
        main_repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha="-deadbeef",
        clean_sha="deadbeef",
    )
    message = build_git_danger_block_message(
        "git push -u origin HEAD:plan/foo",
        worktree,
        rev_parse_head=lambda _cwd: "deadbeef",
        sha_resolves=_record_attempts,
    )
    assert attempted == []
    assert (
        message
        == "push denied: this round's verify-status SHA does not resolve to a commit in this repository"
    )


# --- REQ-027 end to end: the real git subprocesses, no seams --------------


def _real_repo_with_commit(tmp_path: Path) -> Path:
    """A real git repository with one commit on main, so the gate's real
    `git rev-parse HEAD` and `git cat-file -e <sha>^{commit}` subprocesses
    both have something true to establish."""

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    git("init", "-q", "-b", "main")
    (tmp_path / "file.txt").write_text("x\n", encoding="utf-8")
    git("add", ".")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "c1")
    return tmp_path


def test_real_repo_happy_path_authorizes_without_any_seam(tmp_path: Path):
    repo = _real_repo_with_commit(tmp_path)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    _write_record(
        repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha=head,
        clean_sha=head,
    )
    assert (
        build_git_danger_block_message("git push -u origin HEAD:plan/foo", repo) is None
    )


def test_real_repo_recorded_sha_resolving_nowhere_denies_for_that_reason(
    tmp_path: Path,
):
    repo = _real_repo_with_commit(tmp_path)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    _write_record(
        repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha="f" * 40,
        clean_sha=head,
    )
    message = build_git_danger_block_message("git push -u origin HEAD:plan/foo", repo)
    assert (
        message
        == "push denied: this round's verify-status SHA does not resolve to a commit in this repository"
    )


def test_real_repo_option_shaped_recorded_sha_denies_with_the_resolution_reason(
    tmp_path: Path,
):
    # What this establishes: a `-`-prefixed recorded SHA denies with the
    # resolution reason in a real repository, no seams. It does NOT establish
    # anything about git's argv — with the real subprocess the same message
    # arises whether or not the guard short-circuits, because `git cat-file`
    # rejects an option-shaped operand on its own. The short-circuit itself
    # is pinned by
    # test_option_shaped_recorded_sha_is_refused_before_any_resolution_attempt.
    repo = _real_repo_with_commit(tmp_path)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    _write_record(
        repo,
        path_branch="plan/foo",
        record_branch="plan/foo",
        verify_sha="-deadbeef",
        clean_sha=head,
    )
    message = build_git_danger_block_message("git push -u origin HEAD:plan/foo", repo)
    assert (
        message
        == "push denied: this round's verify-status SHA does not resolve to a commit in this repository"
    )
