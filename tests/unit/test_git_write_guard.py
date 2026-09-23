from collections.abc import Callable
from pathlib import Path

import pytest

from agentic_workflows.git_write_guard import (
    build_git_danger_block_message,
    find_dangerous_git_segment,
    is_git_dangerous_command,
)
from agentic_workflows.plan_run_state import (
    PlanRunState,
    record_path_for_branch,
    write_plan_run_state,
)
from agentic_workflows.worktree_capacity import (
    CapacitySnapshot,
    WorktreeCapacityError,
    capacity_snapshot,
)


def _main_checkout_cwd(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    return tmp_path


def _linked_worktree_cwd(tmp_path: Path) -> Path:
    main_repo = tmp_path / "main-repo"
    main_repo.mkdir()
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text(
        f"gitdir: {main_repo}/.git/worktrees/agent-1\n", encoding="utf-8"
    )
    return worktree


def _worktree_pair(tmp_path: Path) -> tuple[Path, Path]:
    """A real main checkout plus a linked worktree of it that is NOT
    agent-owned, so location-override tests are not confounded by the
    agent-worktree relaxation."""
    main_repo = tmp_path / "main-repo"
    (main_repo / ".git").mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text(
        f"gitdir: {main_repo}/.git/worktrees/agent-1\n", encoding="utf-8"
    )
    return main_repo, worktree


def _repo_with_agent_worktree(tmp_path: Path, name: str) -> tuple[Path, Path]:
    """Main checkout plus a real linked worktree at
    <main>/.agents.worktrees/<name>."""
    main_repo = tmp_path / "main-repo"
    (main_repo / ".git" / "worktrees" / name).mkdir(parents=True)
    worktree = main_repo / ".agents.worktrees" / name
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text(
        f"gitdir: {main_repo}/.git/worktrees/{name}\n", encoding="utf-8"
    )
    return main_repo, worktree


def _non_agent_worktree(tmp_path: Path, main_repo: Path) -> Path:
    """A linked worktree of the same `main_repo` sitting OUTSIDE the
    agent-owned root — the shape every worktree created before this rule has."""
    worktree = tmp_path / "legacy-worktree"
    worktree.mkdir()
    (worktree / ".git").write_text(
        f"gitdir: {main_repo}/.git/worktrees/legacy\n", encoding="utf-8"
    )
    return worktree


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git status", False),
        ("git diff --stat", False),
        ("git show HEAD~1", False),
        ("git branch --show-current", False),
        ("git stash list", False),
        ("git worktree list", False),
        ("git reflog", False),
        ("git tag -l 'v*'", False),
        ("FOO=1 git -C repo status", False),
        ("cd repo && git log --oneline", False),
        ("git commit -m 'checkpoint'", True),
        ("git push origin main", True),
        ("git checkout feature-x", True),
        ("git switch -c feature-x", True),
        ("cd repo && git reset --hard", True),
        ("git config --get user.name", True),
        ("git config user.name videobooks", True),
    ],
)
def test_is_git_dangerous_command(command: str, expected: bool):
    assert is_git_dangerous_command(command) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git add .", False),
        ("git add -f ignored_file.txt", False),
        ("git commit -m 'new commit'", True),
        ("git fetch origin", False),
        ("git pull --rebase", False),
        ("git merge feature-x", False),
        ("git rebase main", False),
        ("git rebase -f main", False),
        ("git rebase --force-rebase main", False),
        ("git cherry-pick abc123", False),
        ("git revert abc123", False),
        ("git am some.patch", False),
        ("git rm old_file.py", False),
        ("git mv old.py new.py", False),
        ("git init", False),
        ("git clone https://example.com/repo.git", False),
        ("git notes add -m 'note'", False),
        ("git format-patch HEAD~1", False),
        ("git fetch-pack /path/to/remote", False),
        ("git sparse-checkout set dir1 dir2", False),
        ("git apply patch.diff", False),
    ],
)
def test_now_default_allowed_by_deny_list(command: str, expected: bool):
    assert is_git_dangerous_command(command) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git bisect start", True),
        ("git bisect reset", True),
        ("git checkout main", True),
        ("git checkout -- file.py", True),
        ("git checkout -b feature", True),
        ("git switch main", True),
        ("git switch -c feature", True),
        ("git push", True),
        ("git push --force-with-lease", True),
        ("git update-index --refresh", True),
        ("git send-pack /path/to/remote", True),
        ("git config --list", True),
    ],
)
def test_blocked_without_an_agent_owned_worktree(
    tmp_path: Path, command: str, expected: bool
):
    # Exercised from a real non-agent linked worktree rather than `cwd=None`,
    # so these rows prove the deny list itself, not just fail-closed behavior
    # when no location can be resolved.
    assert is_git_dangerous_command(command, _linked_worktree_cwd(tmp_path)) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git config --list", True),
        ("git config user.name videobooks", True),
        ("git send-pack /path/to/remote", True),
        ("git push", True),
        ("git push --force-with-lease", True),
    ],
)
def test_always_blocked_even_in_an_agent_owned_worktree(
    tmp_path: Path, command: str, expected: bool
):
    # Of the deny list, only these reach shared repository state or the remote,
    # so only these stay blocked no matter where the command runs from.
    _main_repo, worktree = _repo_with_agent_worktree(tmp_path, "wt")
    assert is_git_dangerous_command(command, worktree) is expected


def test_find_dangerous_git_segment_returns_only_the_blocked_segment():
    refused = find_dangerous_git_segment(
        "git status && git push origin main && git diff --stat"
    )
    assert refused is not None
    assert refused.kind == "matched"
    assert refused.segment == "git push origin main"


def test_find_dangerous_git_segment_returns_none_when_nothing_is_dangerous():
    assert find_dangerous_git_segment("git add . && git status") is None


def test_a_parse_failure_and_a_matched_pattern_report_distinct_kinds():
    # REQ-014: the two refusals must be distinguishable in the result itself.
    # Both used to return the raw command text — indistinguishable at the
    # seam — although a parse failure never consulted any git rule.
    parse_failure = find_dangerous_git_segment('git stash drop "unclosed')
    assert parse_failure is not None
    assert parse_failure.kind == "unparseable"
    assert parse_failure.segment == 'git stash drop "unclosed'

    matched = find_dangerous_git_segment("git stash drop stash@{0}")
    assert matched is not None
    assert matched.kind == "matched"
    assert matched.segment == "git stash drop stash@{0}"


def _write_record(main_repo: Path) -> None:
    """A live plan-run record for plan/foo, so a canonical push reaches the
    pushed-SHA resolution — where the injected seam can raise."""
    verify_sha = "deadbeef"
    write_plan_run_state(
        main_repo / record_path_for_branch("plan/foo"),
        PlanRunState(
            status="InProgress",
            branch="plan/foo",
            integration_worktree="",
            verify_status_sha=verify_sha,
            secret_scan_clean_sha=verify_sha,
            pr_url="",
            terminal_outcome="",
        ),
    )


def test_an_evaluation_failure_is_its_own_kind_not_a_parse_failure(
    tmp_path: Path,
):
    # Tokenization succeeds and evaluation itself raises — the injected push
    # seam stands in for a real evaluator error (Task 48 sealed the resolution
    # leaf, so no natural input raises here anymore; the seam net must still
    # fail closed with its own kind). The message layer reports an evaluation
    # failure as a git block and never as a parse failure (REQ-014); the seam
    # must make the same distinction its docstring admitted conflating.
    main_repo = _main_checkout_cwd(tmp_path)
    _write_record(main_repo)

    def raising_seam(_location: Path) -> str | None:
        raise ValueError("injected evaluator failure")

    command = "git push -u origin HEAD:plan/foo"
    refused = find_dangerous_git_segment(
        command,
        main_repo,
        rev_parse_head=raising_seam,
        sha_resolves=lambda _location, _sha: True,
    )

    assert refused is not None
    assert refused.kind == "unevaluable"
    assert refused.kind != "unparseable"


def test_build_git_danger_block_message_describes_deny_list_policy():
    # A non-push blocked subcommand keeps the generic deny-list message. Push
    # now carries its own specific authorization-denial reason instead (see
    # the push message tests below), so exercise the generic path with
    # send-pack, one of the two unconditionally blocked subcommands.
    message = build_git_danger_block_message("git send-pack /path/to/remote")
    assert message is not None
    assert "git send-pack /path/to/remote" in message
    assert "Most git operations are allowed" in message
    assert "git writes must not run from agent sessions" not in message


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git status --no-verify", True),
        ("git diff --stat --no-verify", True),
        ("git status", False),
        ("git diff --stat", False),
    ],
)
def test_no_verify_blocked_by_default_without_cwd(command: str, expected: bool):
    # No cwd means the caller couldn't establish a linked-worktree location,
    # so the guard fails closed and blocks --no-verify unconditionally.
    assert is_git_dangerous_command(command) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git commit -m 'new commit'", True),
        ("git commit --amend -m 'fixup'", True),
        ("git commit --amend", True),
        ("git commit --no-verify -m 'skip hooks'", True),
        ("git commit --amend --no-verify", True),
    ],
)
def test_commit_blocked_by_default_without_cwd(command: str, expected: bool):
    # No cwd means the caller couldn't establish a linked-worktree location,
    # so the guard fails closed and blocks commit unconditionally.
    assert is_git_dangerous_command(command) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git status --no-verify", True),
        ("git commit --no-verify -m 'skip hooks'", True),
        ("git commit --amend --no-verify", True),
    ],
)
def test_no_verify_blocked_from_main_checkout_cwd(
    tmp_path: Path, command: str, expected: bool
):
    assert is_git_dangerous_command(command, _main_checkout_cwd(tmp_path)) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git status --no-verify", False),
        ("git commit --no-verify -m 'skip hooks'", False),
        ("git commit --amend --no-verify", False),
    ],
)
def test_no_verify_allowed_from_linked_worktree_cwd(
    tmp_path: Path, command: str, expected: bool
):
    assert is_git_dangerous_command(command, _linked_worktree_cwd(tmp_path)) is expected


def test_no_verify_follows_the_location_override_like_commit(tmp_path: Path):
    # `--no-verify` used to read raw `cwd` while `commit`, `push` and the
    # agent-worktree relaxation all resolved -C/--git-dir/--work-tree first.
    # `git -C <worktree> ...` is the form the rule files recommend, because the
    # hook sees `cwd` as a pre-command snapshot, so the disagreement made the
    # recommended form silently fail for `--no-verify` alone.
    main_repo, worktree = _worktree_pair(tmp_path)
    into_worktree = f"git -C {worktree} commit --no-verify -m x"
    into_main = f"git -C {main_repo} commit --no-verify -m x"
    # Now matches the plain `git -C <worktree> commit -m x` case.
    assert is_git_dangerous_command(into_worktree, main_repo) is False
    # The bypass `_commit_is_from_linked_worktree` closes must not reopen.
    assert is_git_dangerous_command(into_main, worktree) is True
    # A non-commit carrier aimed at the main checkout is blocked too — this
    # one used to slip through, because raw `cwd` was a worktree.
    assert (
        is_git_dangerous_command(f"git -C {main_repo} status --no-verify", worktree)
        is True
    )


@pytest.mark.parametrize(
    "command",
    [
        # Blocked by `reset --hard`: the override target is a linked worktree
        # but not an agent-owned one, so the relaxation does not apply.
        "git -C {worktree} reset --hard --no-verify",
        # Blocked by the push chain, which `--no-verify` never reached anyway.
        "git -C {worktree} push --no-verify",
    ],
)
def test_no_verify_override_does_not_relax_any_other_rule(tmp_path: Path, command: str):
    main_repo, worktree = _worktree_pair(tmp_path)
    assert (
        is_git_dangerous_command(command.format(worktree=worktree), main_repo) is True
    )


@pytest.mark.parametrize(
    "command",
    ["git status --no-verify", "git commit --no-verify -m x"],
)
def test_no_verify_still_fails_closed_without_a_resolvable_location(
    tmp_path: Path, command: str
):
    # No cwd and no override leaves nothing to resolve; a cwd with no `.git`
    # marker resolves to something that is not a linked worktree.
    orphan = tmp_path / "not-a-repo"
    orphan.mkdir()
    assert is_git_dangerous_command(command) is True
    assert is_git_dangerous_command(command, orphan) is True


def test_no_verify_allowed_from_a_subdirectory_of_a_linked_worktree(tmp_path: Path):
    subdir = _linked_worktree_cwd(tmp_path) / "src" / "utils"
    subdir.mkdir(parents=True)
    assert is_git_dangerous_command("git commit --no-verify -m x", subdir) is False


def test_no_verify_blocked_when_cwd_has_no_git_marker(tmp_path: Path):
    orphan = tmp_path / "not-a-repo"
    orphan.mkdir()
    assert is_git_dangerous_command("git commit --no-verify -m x", orphan) is True


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git checkout main --no-verify", True),
        ("git push --no-verify", True),
        ("git reset --hard --no-verify", True),
    ],
)
def test_other_blocked_patterns_stay_blocked_in_a_non_agent_owned_worktree_despite_no_verify(
    tmp_path: Path, command: str, expected: bool
):
    # --no-verify only exempts the blanket no-verify rule; it must not
    # relax any other independently-dangerous pattern.
    assert is_git_dangerous_command(command, _linked_worktree_cwd(tmp_path)) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git config --get user.name", True),
        ("git config --global --get user.email", True),
        ("git config --list", True),
        ("git config user.name videobooks", True),
        ("git config --global user.email a@b.com", True),
    ],
)
def test_config_always_blocked(command: str, expected: bool):
    assert is_git_dangerous_command(command) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git reset --hard", True),
        ("git reset --hard HEAD~1", True),
        ("git reset", False),
        ("git reset some/path", False),
        ("git reset --soft HEAD~1", False),
        ("git reset --mixed HEAD~1", False),
        ("git reset HEAD~1", False),
    ],
)
def test_reset_blocked_only_with_hard_flag(command: str, expected: bool):
    assert is_git_dangerous_command(command) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git clean -n", False),
        ("git clean --dry-run", False),
        ("git clean -n -fdx", False),
        ("git clean -fd", True),
        ("git clean -f", True),
    ],
)
def test_clean_blocked_unless_dry_run(command: str, expected: bool):
    assert is_git_dangerous_command(command) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git restore file.py", True),
        ("git restore --force file.py", True),
        ("git restore --staged file.py", False),
        ("git restore -S file.py", False),
        ("git restore --staged --worktree file.py", False),
    ],
)
def test_restore_blocked_unless_staged(command: str, expected: bool):
    assert is_git_dangerous_command(command) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git branch -D old-feature", True),
        ("git branch --delete --force old-feature", True),
        ("git branch -d merged-feature", False),
        ("git branch new-feature", False),
        ("git branch -m old-name new-name", False),
        ("git branch -f other-branch abc123", False),
        ("git branch --show-current", False),
        # One non-agent operand poisons the whole invocation.
        ("git branch -D sdd/foo main", True),
        # No operand at all fails closed.
        ("git branch -D", True),
        # The prefix is `sdd/`, not the bare word.
        ("git branch -D sdd", True),
        # Every non-option token counts as an operand, so a value-taking
        # option can never hide a non-agent branch name behind it.
        ("git branch --sort main -D sdd/x", True),
    ],
)
def test_branch_force_delete_blocked_for_non_agent_names(command: str, expected: bool):
    assert is_git_dangerous_command(command) is expected


@pytest.mark.parametrize(
    "command",
    [
        "git branch -D sdd/x",
        "git branch --delete --force plan/y",
        "git branch -D sdd/a sdd/b plan/c",
        "git branch -Df plan/z",
        "git branch -D --quiet sdd/x",
    ],
)
def test_branch_force_delete_allowed_for_agent_branch_prefixes(command: str):
    # Force-deleting a branch this workflow created is its own cleanup, so the
    # two namespaces it owns are carved out of the force-delete block.
    assert is_git_dangerous_command(command) is False


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git tag -f v1.0.0", True),
        ("git tag --force v1.0.0 abc123", True),
        ("git tag v1.0.0", False),
        ("git tag -d v1.0.0", True),
        ("git tag --delete v1.0.0", True),
        ("git tag -l 'v*'", False),
    ],
)
def test_tag_blocked_on_force_or_delete(command: str, expected: bool):
    # The spec's permission matrix denies `git tag -f` AND `-d` in every tier:
    # both mutate the one tag namespace every worktree resolves identically.
    assert is_git_dangerous_command(command) is expected


# The stash form matrix (REQ-005, REQ-005a, DD-001): an invocation is denied
# when it DESTROYS a shared-stack entry outright (`drop`/`clear`, whatever they
# name) or takes one back OFF the stack by POSITION — a stack reference, or the
# stack top an operand-less take-back defaults to. `pop` is denied in every
# spelling: it removes an entry by construction and rejects a hash operand
# outright (measured in a throwaway repo), so no pop form names an identity.
# Naming the stash COMMIT's hash is identity: apply/branch by hash remove no
# entry (measured — only the stack-reference form of `branch` drops), and every
# add-only form (`push`/`create`/`store` — `store` is what both measured
# recoveries used) plus the read-only forms stay permitted. Flags and a `--`
# separator never hide the operand from the positional read.
@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git stash drop", True),
        ("git stash clear", True),
        ("git stash drop stash@{0}", True),
        ("git stash pop", True),
        ("git stash pop stash@{2}", True),
        ("git stash pop --index", True),
        ("git stash apply", True),
        ("git stash apply stash@{0}", True),
        ("git stash apply refs/stash", True),
        ("git stash apply ''", True),
        ("git stash apply --quiet stash@{0}", True),
        ("git stash apply --index stash@{0}", True),
        ("git stash apply -- stash@{0}", True),
        ("git stash branch take-back", True),
        ("git stash branch take-back stash@{1}", True),
        ("git stash apply 9e7e9ab", False),
        ("git stash apply 9e7e9abac52286fbd31c317a3801eed37c5e8219", False),
        ("git stash apply --quiet 9e7e9ab", False),
        ("git stash apply -- 9e7e9ab", False),
        ("git stash branch from-hash 9e7e9ab", False),
        ("git stash", False),
        ("git stash push -m save", False),
        ("git stash create", False),
        ("git stash store 9e7e9abac52286fbd31c317a3801eed37c5e8219", False),
        ("git stash list", False),
        ("git stash show", False),
    ],
)
def test_stash_denied_on_destruction_or_positional_take_back(
    command: str, expected: bool
):
    assert is_git_dangerous_command(command) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git reflog expire --expire=now --all", True),
        ("git reflog delete HEAD@{1}", True),
        ("git reflog", False),
        ("git reflog show", False),
        ("git reflog list", False),
        ("git reflog exists refs/heads/main", False),
    ],
)
def test_reflog_blocked_only_on_expire_or_delete(command: str, expected: bool):
    assert is_git_dangerous_command(command) is expected


# --- worktree add / forced remove: agent-owned target authorization ------


@pytest.mark.parametrize("action", ["add", "remove -f", "remove --force"])
@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (".agents.worktrees/x", False),
        # A DIRECT child only — one level deeper is not the agent-owned root.
        (".agents.worktrees/x/y", True),
        (".agents/x", True),
        # The legacy root gets no grandfather clause.
        (".worktrees/x", True),
        ("/tmp/elsewhere", True),
        # The shell expands `~`, so the guard only ever sees the literal
        # string — which resolves to a `~` directory, not the home directory.
        ("~/x", True),
    ],
)
def test_worktree_add_and_forced_remove_require_agent_owned_target(
    tmp_path: Path, action: str, target: str, expected: bool
):
    main_repo, _worktree = _repo_with_agent_worktree(tmp_path, "wt")
    command = f"git worktree {action} {target}"
    assert is_git_dangerous_command(command, main_repo) is expected


@pytest.mark.parametrize(
    "command",
    [
        "git worktree remove ../anything",
        "git worktree remove /tmp/x",
        "git worktree remove .agents.worktrees/wt",
    ],
)
def test_non_forced_worktree_remove_stays_unrestricted(tmp_path: Path, command: str):
    # The deliberate non-change: git itself refuses a non-forced remove of a
    # dirty worktree, so it cannot destroy uncommitted work and needs no
    # path-based authorization of its own.
    main_repo, _worktree = _repo_with_agent_worktree(tmp_path, "wt")
    assert is_git_dangerous_command(command, main_repo) is False


@pytest.mark.parametrize(
    ("add_args", "expected"),
    [
        ("-b sdd/x .agents.worktrees/y", False),
        # The `-b` VALUE must never be mistaken for the path operand.
        ("-b .agents.worktrees/y /elsewhere", True),
        ("-B .agents.worktrees/y /elsewhere", True),
        ("--lock --reason .agents.worktrees/y /elsewhere", True),
        # Attached forms are single tokens starting with `-`, so they are
        # skipped as plain flags and the next token is the real operand.
        ("-bsdd/x .agents.worktrees/y", False),
        ("-bsdd/x /elsewhere", True),
        ("--reason=why .agents.worktrees/y", False),
        ("--reason=why /elsewhere", True),
        ("-f --detach .agents.worktrees/y HEAD~1", False),
        # Fail closed when no path operand can be found at all.
        ("", True),
        ("-b sdd/x", True),
    ],
)
def test_worktree_add_path_operand_survives_flag_values(
    tmp_path: Path, add_args: str, expected: bool
):
    main_repo, _worktree = _repo_with_agent_worktree(tmp_path, "wt")
    command = f"git worktree add {add_args}".rstrip()
    assert is_git_dangerous_command(command, main_repo) is expected


@pytest.mark.parametrize(
    "command",
    [
        "git worktree list",
        "git worktree prune",
        "git worktree lock ../x",
        "git worktree unlock ../x",
        "git worktree move a b",
        "git worktree",
    ],
)
def test_worktree_actions_without_a_path_target_are_unaffected(command: str):
    # Only `add` and `remove --force` authorize against a path, so every other
    # action stays allowed even with no cwd to resolve anything against.
    assert is_git_dangerous_command(command) is False


@pytest.mark.parametrize("action", ["add", "remove -f"])
@pytest.mark.parametrize(
    "prefix",
    [
        # No session cwd and no -C: nothing to resolve a relative operand
        # against.
        "",
        # A relative -C cannot be resolved without a cwd either.
        "-C sub ",
    ],
)
def test_worktree_target_fails_closed_when_resolution_base_is_unknowable(
    tmp_path: Path, prefix: str, action: str
):
    _main_repo, _worktree = _repo_with_agent_worktree(tmp_path, "wt")
    command = f"git {prefix}worktree {action} .agents.worktrees/wt"
    assert is_git_dangerous_command(command, None) is True


@pytest.mark.parametrize("action", ["add", "remove --force"])
@pytest.mark.parametrize(
    "cwd_kind", ["main", "main-subdir", "agent-worktree", "non-agent-worktree"]
)
def test_worktree_target_resolves_relative_operand_against_dash_c(
    tmp_path: Path, cwd_kind: str, action: str
):
    # `git -C <dir>` makes git chdir to <dir> first, so a relative operand
    # resolves against <dir>. That is documented git behavior, and `-C` is the
    # form the rule files recommend, so refusing it blocked the workflow's own
    # natural command shape.
    main_repo, agent_worktree = _repo_with_agent_worktree(tmp_path, "wt")
    subdir = main_repo / "src"
    subdir.mkdir()
    cwds = {
        "main": main_repo,
        "main-subdir": subdir,
        "agent-worktree": agent_worktree,
        "non-agent-worktree": _non_agent_worktree(tmp_path, main_repo),
    }
    command = f"git -C {main_repo} worktree {action} .agents.worktrees/wt"
    assert is_git_dangerous_command(command, cwds[cwd_kind]) is False


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        # Repeated -C compound relative to each other, as git documents.
        ("-C {main} -C .agents", True),
        ("-C {main}/src -C ..", False),
        # A later absolute -C replaces whatever came before it.
        ("-C {away} -C {main}", False),
        # -C beats a --work-tree that names somewhere else entirely.
        ("-C {main} --work-tree={away}", False),
    ],
)
def test_repeated_dash_c_options_compound(tmp_path: Path, options: str, expected: bool):
    main_repo, _worktree = _repo_with_agent_worktree(tmp_path, "wt")
    (main_repo / "src").mkdir()
    away = tmp_path / "away"
    away.mkdir()
    resolved = options.format(main=main_repo, away=away)
    command = f"git {resolved} worktree remove --force .agents.worktrees/wt"
    assert is_git_dangerous_command(command, main_repo) is expected


def test_worktree_target_follows_dash_c_out_of_the_repo(tmp_path: Path):
    # Resolving the operand the way git would cannot authorize a target git
    # would not act on: with -C pointing outside, the same relative operand
    # names a directory outside the agent root.
    main_repo, _worktree = _repo_with_agent_worktree(tmp_path, "wt")
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / ".agents.worktrees" / "wt").mkdir(parents=True)
    command = f"git -C {elsewhere} worktree remove --force .agents.worktrees/wt"
    assert is_git_dangerous_command(command, main_repo) is True


@pytest.mark.parametrize(
    "prefix",
    ["--git-dir={main}/.git ", "--work-tree={main} ", "--git-dir {main}/.git "],
)
def test_non_chdir_location_options_leave_the_operand_on_the_session_cwd(
    tmp_path: Path, prefix: str
):
    # Neither `--git-dir` nor `--work-tree` changes git's working directory, so
    # a relative operand still resolves against the session cwd. From <main>/src
    # that lands outside the agent root — unlike the `-C` form below, which is
    # the same command with the only difference being the option.
    main_repo, _worktree = _repo_with_agent_worktree(tmp_path, "wt")
    subdir = main_repo / "src"
    subdir.mkdir()
    tail = "worktree remove --force .agents.worktrees/wt"
    assert is_git_dangerous_command(
        f"git {prefix.format(main=main_repo)}{tail}", subdir
    )
    assert is_git_dangerous_command(f"git -C {main_repo} {tail}", subdir) is False


@pytest.mark.parametrize(
    "prefix",
    [
        "",
        "-C {main} ",
        "-C {elsewhere} ",
        "--git-dir {main}/.git ",
        "--work-tree {main} ",
    ],
)
@pytest.mark.parametrize("agent_owned", [True, False])
def test_absolute_worktree_operands_ignore_every_location_option(
    tmp_path: Path, prefix: str, agent_owned: bool
):
    # An absolute operand is already fully determined, so no location option
    # can move it in either direction.
    main_repo, _worktree = _repo_with_agent_worktree(tmp_path, "wt")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    target = (
        main_repo / ".agents.worktrees" / "x" if agent_owned else elsewhere / "x"
    )
    resolved = prefix.format(main=main_repo, elsewhere=elsewhere)
    command = f"git {resolved}worktree remove --force {target}"
    assert is_git_dangerous_command(command, main_repo) is not agent_owned


@pytest.mark.parametrize(
    ("subdir", "target", "expected"),
    [
        ("", ".agents.worktrees/x", False),
        ("", ".agents.worktrees/x/", False),
        ("src", "../.agents.worktrees/x", False),
        # Resolving against the subdirectory instead of the main checkout would
        # make <main>/src/.agents.worktrees/x look agent-owned. It is not.
        ("src", ".agents.worktrees/x", True),
    ],
)
def test_worktree_target_resolves_relative_operand_against_session_cwd(
    tmp_path: Path, subdir: str, target: str, expected: bool
):
    main_repo, _worktree = _repo_with_agent_worktree(tmp_path, "wt")
    cwd = main_repo / subdir if subdir else main_repo
    cwd.mkdir(parents=True, exist_ok=True)
    command = f"git worktree add {target}"
    assert is_git_dangerous_command(command, cwd) is expected


def test_worktree_target_symlinked_out_of_the_agent_root_is_blocked(tmp_path: Path):
    # The operand is fully resolved, so a symlink sitting at an agent-owned
    # name but pointing elsewhere does not inherit the root's permission.
    main_repo, _worktree = _repo_with_agent_worktree(tmp_path, "wt")
    outside = tmp_path / "outside"
    outside.mkdir()
    link = main_repo / ".agents.worktrees" / "x"
    link.symlink_to(outside)
    command = f"git worktree remove -f {link}"
    assert is_git_dangerous_command(command, main_repo) is True


@pytest.mark.parametrize(
    "cwd_kind", ["main", "main-subdir", "agent-worktree", "non-agent-worktree"]
)
def test_agent_ownership_anchors_on_the_main_checkout_from_any_worktree(
    tmp_path: Path, cwd_kind: str
):
    # Ownership is anchored on the main checkout the session belongs to, so the
    # same absolute target is agent-owned no matter which of its checkouts the
    # command is issued from.
    main_repo, agent_worktree = _repo_with_agent_worktree(tmp_path, "wt")
    subdir = main_repo / "src"
    subdir.mkdir()
    cwds = {
        "main": main_repo,
        "main-subdir": subdir,
        "agent-worktree": agent_worktree,
        "non-agent-worktree": _non_agent_worktree(tmp_path, main_repo),
    }
    target = main_repo / ".agents.worktrees" / "target"
    command = f"git worktree add {target}"
    assert is_git_dangerous_command(command, cwds[cwd_kind]) is False


# --- worktree add: capacity backstop in the hook seam (REQ-009, REQ-010) --


def _capacity_probe(
    main_repo: Path,
    *,
    max_concurrent: int,
    listed_agent_worktrees: list[str],
) -> Callable[[Path], CapacitySnapshot]:
    """A production-shaped probe: the SHARED capacity module's
    `capacity_snapshot` over a real temp config file and an injected porcelain
    listing, so the guard is judged by the same counting rule the acquire
    script uses — never a test-private one."""
    config_path = main_repo / ".agents" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        f"[worktrees]\nmax_concurrent = {max_concurrent}\n", encoding="utf-8"
    )
    porcelain = f"worktree {main_repo}\n\n" + "".join(
        f"worktree {main_repo / '.agents.worktrees' / name}\n"
        f"branch refs/heads/sdd/{name}\n\n"
        for name in listed_agent_worktrees
    )

    def probe(repo_root: Path) -> CapacitySnapshot:
        return capacity_snapshot(
            repo_root,
            config_path=config_path,
            worktree_lister=lambda _root: porcelain,
        )

    return probe


@pytest.mark.parametrize(
    ("max_concurrent", "denied"),
    [
        (1, True),
        (2, False),
    ],
)
def test_raw_worktree_add_denied_past_cap_allowed_under_cap(
    tmp_path: Path, max_concurrent: int, denied: bool
):
    # The hook seam's capacity backstop: with the cap full, a raw
    # `git worktree add` against an agent-owned target is denied and pointed
    # at the acquire script; with a slot free, today's agent-owned-root
    # authorization is unchanged.
    main_repo, _existing = _repo_with_agent_worktree(tmp_path, "wt")
    target = main_repo / ".agents.worktrees" / "next"
    command = f"git worktree add {target}"
    message = build_git_danger_block_message(
        command,
        main_repo,
        capacity_probe=_capacity_probe(
            main_repo, max_concurrent=max_concurrent, listed_agent_worktrees=["wt"]
        ),
    )
    assert (message is not None) is denied
    if denied:
        assert message is not None
        assert "cap is full (1 of 1" in message
        assert "scripts/worktree_acquire.py" in message
        # The suggested command must be runnable as printed: acquire's
        # argparse requires --run, so a hint omitting it would exit 2 the
        # moment the agent pasted it (review-final item 2).
        assert "acquire --name <name> --branch <branch> --run <run>" in message
    # The capacity question lives in the hook seam only: the danger-pattern
    # classifier stays capacity-blind, so the ownership contract it carries is
    # judged identically whether the cap is full or not.
    assert is_git_dangerous_command(command, main_repo) is False


def test_undecidable_capacity_denies_the_raw_add_fail_closed(tmp_path: Path):
    # An unreadable cap input must not become an allow: a denial naming the
    # broken input preserves the cap, where a guessed allow would silently
    # unbound it. The script stays the escape hatch — it fails on the same
    # input with exit 2.
    main_repo, _existing = _repo_with_agent_worktree(tmp_path, "wt")
    target = main_repo / ".agents.worktrees" / "next"

    def undecidable(repo_root: Path) -> CapacitySnapshot:
        raise WorktreeCapacityError(
            f"{(repo_root / '.agents' / 'config.toml').as_posix()} is missing "
            "its worktrees.max_concurrent key"
        )

    message = build_git_danger_block_message(
        f"git worktree add {target}", main_repo, capacity_probe=undecidable
    )
    assert message is not None
    assert "could not be decided" in message
    assert "worktrees.max_concurrent" in message
    assert "scripts/worktree_acquire.py" in message
    # Same runnable-hint invariant as the cap-full denial: the pasted
    # command must carry acquire's required --run (review-final item 2).
    assert "acquire --name <name> --branch <branch> --run <run>" in message


@pytest.mark.parametrize(
    "probe_error",
    [
        OSError("git worktree list was killed by a full disk"),
        RuntimeError("symlink loop while resolving the agent worktree root"),
        # A bare ValueError — e.g. `Path.resolve()` on an embedded NUL — is
        # the shape the catch tuple missed: WorktreeCapacityError SUBCLASSES
        # ValueError, so the tuple never caught the base-class raise.
        ValueError("embedded null byte in the worktree path"),
    ],
    ids=["os-error", "runtime-error", "value-error"],
)
def test_crashing_probe_denies_the_raw_add_fail_closed(
    tmp_path: Path, probe_error: Exception
):
    # A probe that CRASHES (a failed listing subprocess, a resolution error)
    # must not escape the hook seam: the hook would exit on the traceback as a
    # non-blocking error and an at-cap raw add would proceed with no cap and
    # no denial anywhere. The crash is refused exactly like an undecidable
    # input — a denial naming the failure, never an allow.
    main_repo, _existing = _repo_with_agent_worktree(tmp_path, "wt")
    target = main_repo / ".agents.worktrees" / "next"

    def crashing(repo_root: Path) -> CapacitySnapshot:
        raise probe_error

    message = build_git_danger_block_message(
        f"git worktree add {target}", main_repo, capacity_probe=crashing
    )
    assert message is not None
    assert "could not be decided" in message
    assert str(probe_error) in message
    assert "scripts/worktree_acquire.py" in message


def test_run_record_with_unresolvable_worktree_value_denies_fail_closed(
    tmp_path: Path,
):
    # The natural source of the bare-ValueError escape: a run record whose
    # `Integration worktree:` value carries an embedded NUL cannot be
    # resolved, so whether the recorded worktree is listed is undecidable —
    # `Path.resolve()` raises there. The probe converts that to the capacity
    # module's fail-closed error naming the field, and the hook seam turns it
    # into the denial — never a crash the hook would report as non-blocking
    # while an at-cap raw add proceeds.
    main_repo, _existing = _repo_with_agent_worktree(tmp_path, "wt")
    target = main_repo / ".agents.worktrees" / "next"
    config_path = main_repo / ".agents" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("[worktrees]\nmax_concurrent = 1\n", encoding="utf-8")
    porcelain = (
        f"worktree {main_repo}\n\n"
        f"worktree {main_repo / '.agents.worktrees' / 'wt'}\n"
        "branch refs/heads/sdd/wt\n\n"
    )
    records_dir = main_repo / record_path_for_branch("plan/run-slug").parent
    write_plan_run_state(
        records_dir / record_path_for_branch("plan/run-slug").name,
        PlanRunState(
            status="InProgress",
            branch="plan/run-slug",
            integration_worktree=(
                f"{main_repo / '.agents.worktrees' / 'recorded'}\x00"
            ),
            verify_status_sha="",
            secret_scan_clean_sha="",
            pr_url="",
            terminal_outcome="",
        ),
    )

    def poisoned_record_probe(repo_root: Path) -> CapacitySnapshot:
        return capacity_snapshot(
            repo_root,
            config_path=config_path,
            records_dir=records_dir,
            worktree_lister=lambda _root: porcelain,
        )

    message = build_git_danger_block_message(
        f"git worktree add {target}", main_repo, capacity_probe=poisoned_record_probe
    )
    assert message is not None
    assert "could not be decided" in message
    assert "Integration worktree" in message
    assert "scripts/worktree_acquire.py" in message


def test_default_probe_anchors_the_cap_config_on_the_main_checkout(tmp_path: Path):
    # With no injected probe, the guard resolves `.agents/config.toml` under
    # the command's own main checkout — never the hook process's working
    # directory (the W0 review's CWD-relative flag, closed at this consumer).
    # The fixture repo has no config of its own, so a denial naming ITS path
    # proves the anchor: pytest's CWD (the real repo, which has a config) was
    # never consulted.
    main_repo, _existing = _repo_with_agent_worktree(tmp_path, "wt")
    target = main_repo / ".agents.worktrees" / "next"
    message = build_git_danger_block_message(f"git worktree add {target}", main_repo)
    assert message is not None
    assert "scripts/worktree_acquire.py" in message
    assert (main_repo / ".agents" / "config.toml").as_posix() in message


def test_forced_remove_stays_allowed_when_the_cap_is_full(tmp_path: Path):
    # Removing a worktree FREES a slot, so the backstop must never gate the
    # cleanup path: at a full cap, the agent-owned forced remove keeps working.
    main_repo, existing = _repo_with_agent_worktree(tmp_path, "wt")
    message = build_git_danger_block_message(
        f"git worktree remove --force {existing}",
        main_repo,
        capacity_probe=_capacity_probe(
            main_repo, max_concurrent=1, listed_agent_worktrees=["wt"]
        ),
    )
    assert message is None


def test_capacity_backstop_does_not_mask_the_ownership_denial(tmp_path: Path):
    # A target outside the agent root is denied for OWNERSHIP, with the
    # generic policy message — never redirected to the script, which would
    # refuse it too: the two denials must stay distinguishable.
    main_repo, _existing = _repo_with_agent_worktree(tmp_path, "wt")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    message = build_git_danger_block_message(
        f"git worktree add {outside}",
        main_repo,
        capacity_probe=_capacity_probe(
            main_repo, max_concurrent=5, listed_agent_worktrees=[]
        ),
    )
    assert message is not None
    assert "Blocked dangerous git command" in message
    assert "scripts/worktree_acquire.py" not in message


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git submodule update --force", True),
        ("git submodule add -f https://example.com/repo.git vendor/repo", True),
        ("git submodule update --init --recursive", False),
        ("git submodule add https://example.com/repo.git vendor/repo", False),
        ("git submodule sync", False),
    ],
)
def test_submodule_blocked_only_on_force(command: str, expected: bool):
    assert is_git_dangerous_command(command) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        # git branch: -D alone, and -d/-f bundled in either order.
        ("git branch -df old-feature", True),
        ("git branch -Df old-feature", True),
        ("git branch -fd old-feature", True),
        # git tag: -f bundled with -a (annotate) in either order.
        ("git tag -fa v1.0.0", True),
        ("git tag -af v1.0.0", True),
        # git tag -F (capital, "read message from file") must NOT be treated
        # as force: lowercase "f" is not a substring of uppercase "F".
        ("git tag -F message.txt v1.0.0", False),
        ("git tag -a v1.0.0 -m msg", False),
        # git submodule update: -N (--no-fetch) and -f (--force) are both
        # real boolean short flags on `update`, confirmed bundlable via
        # `git submodule -h` (both take no argument) and git's generic
        # parse-options bundling behavior (verified empirically with
        # `git branch -va` producing identical output to `git branch -v -a`).
        ("git submodule update -Nf", True),
        ("git submodule update -fN", True),
    ],
)
def test_bundled_short_flags_detected_in_force_family(command: str, expected: bool):
    assert is_git_dangerous_command(command) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git gc --aggressive", True),
        ("git gc --prune=now", True),
        ("git gc --prune=all", True),
        ("git gc --prune", True),
        ("git gc", False),
        ("git gc --auto", False),
    ],
)
def test_gc_blocked_only_on_aggressive_or_prune(command: str, expected: bool):
    assert is_git_dangerous_command(command) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git remote -v", False),
        ("git remote get-url origin", False),
        ("git remote show origin", False),
        ("git remote add origin https://example.com/repo.git", True),
        ("git remote remove origin", True),
        ("git remote set-url origin https://example.com/repo.git", True),
    ],
)
def test_remote_behavior_is_unchanged(command: str, expected: bool):
    assert is_git_dangerous_command(command) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("sudo git push origin main", True),
        ("sudo git status", False),
        ("sudo -u root git reset --hard", True),
    ],
)
def test_sudo_prefix_is_still_stripped_before_classification(
    command: str, expected: bool
):
    assert is_git_dangerous_command(command) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git add -A\ngit push --force", True),
        ("git status\ngit push origin main", True),
        ("git add -A\ngit reset --hard", True),
        ("git add -A\ngit status", False),
        ('git commit -m "line1\nline2"', True),
        ("git add -A\n\ngit push --force", True),
    ],
)
def test_newline_separated_commands_are_each_classified(command: str, expected: bool):
    assert is_git_dangerous_command(command) is expected


def test_newline_inside_quotes_stays_in_one_segment_not_split():
    # The embedded newline lives inside a quoted -m value; it must remain part
    # of a single token/segment rather than being treated as a `;` separator.
    segment_refusal = find_dangerous_git_segment(
        'git commit -m "line1\nline2" --no-verify'
    )
    assert segment_refusal is not None
    assert segment_refusal.kind == "matched"
    assert segment_refusal.segment == "git commit -m line1\nline2 --no-verify"


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ('git push "unterminated', True),
        ('git status "unterminated', True),
        ("echo 'unterminated", True),
        ('git add -A\ngit commit -m "unterminated', True),
    ],
)
def test_unparseable_shell_input_fails_closed(command: str, expected: bool):
    assert is_git_dangerous_command(command) is expected


#: A command the tokenizer genuinely cannot resolve: one quote, never closed.
#:
#: This was a heredoc whose body contained an apostrophe, which is the shape
#: A-011 actually reported. Main has since taught the parser to cut a heredoc
#: body out before tokenizing, so that command now parses cleanly and is
#: correctly allowed -- the underlying cause was fixed rather than reported
#: better. The refusal path it exercised is still real and still reachable, so
#: the fixture moves to a command that still reaches it rather than the test
#: being deleted along with the example that motivated it.
_A_QUOTE_NEVER_CLOSED = 'git status "unclosed'


def test_unparseable_says_unparseable_rather_than_naming_a_git_prohibition():
    message = build_git_danger_block_message(_A_QUOTE_NEVER_CLOSED)

    assert message is not None, "fail-closed: an unparseable command still refuses"
    assert "could not be parsed" in message
    assert "git command" not in message
    assert "git operations are allowed" not in message


def test_unparseable_refusal_names_the_workaround():
    message = build_git_danger_block_message(_A_QUOTE_NEVER_CLOSED)

    assert message is not None
    assert "could not be parsed" in message, "positive control: the parse branch ran"
    assert "run that file" in message
    # The trigger clause names where an apostrophe can actually reach the
    # tokenizer: heredoc bodies are cut out before tokenizing (measured), so
    # only one OUTSIDE a heredoc body can — the old "inside" wording was
    # measured false.
    assert "outside a heredoc body" in message
    assert "inside a heredoc body" not in message


@pytest.mark.parametrize(
    ("command", "expected_reason"),
    [
        ("echo 'unterminated", "a quote is opened and never closed"),
        ("echo trailing\\", "the command ends in a trailing backslash"),
    ],
)
def test_unparseable_refusal_names_the_specific_parse_failure(
    command: str, expected_reason: str
):
    # Two distinct reasons, so a single hardcoded phrase cannot satisfy both.
    message = build_git_danger_block_message(command)

    assert message is not None
    assert expected_reason in message


def test_unparseable_refusal_does_not_echo_the_command_back():
    # The guard reads arbitrary shell text, so an unparseable command can carry
    # a credential. This canary stands in for one; its literal shape is
    # deliberately not scanner-bait.
    canary = "ExampleBearerCredentialCanary"
    command = f"curl -H 'Authorization: Bearer {canary} https://example.invalid/v1"

    message = build_git_danger_block_message(command)

    assert message is not None
    assert "could not be parsed" in message, "positive control: the parse branch ran"
    assert canary not in message
    assert "example.invalid" not in message
    assert "curl" not in message


def test_a_value_error_raised_after_parsing_still_reports_a_git_block(tmp_path: Path):
    # An embedded NUL makes `Path.resolve()` raise ValueError deep inside
    # worktree-ownership resolution, long after tokenization has succeeded. It
    # reaches the same handler and must not be relabelled a parse failure.
    main_repo = _main_checkout_cwd(tmp_path)
    agent_owned = main_repo / ".agents.worktrees" / "wt"
    parseable = f"git worktree add {agent_owned}"

    assert (
        build_git_danger_block_message(
            parseable,
            main_repo,
            # The capacity backstop judges an agent-owned add even when no danger
            # pattern matches, so "authorized" now means under-cap too: pin the
            # cap dimension so the refusal below can only come from the NUL.
            capacity_probe=_capacity_probe(
                main_repo, max_concurrent=2, listed_agent_worktrees=[]
            ),
        )
        is None
    ), (
        "control: the same command without the NUL is authorized, so a refusal "
        "below can only come from the post-parse ValueError"
    )

    message = build_git_danger_block_message(f"{parseable}{chr(0)}", main_repo)

    assert message is not None, "fail-closed behaviour unchanged"
    assert "could not be parsed" not in message
    assert "Blocked dangerous git command" in message


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git commit -m 'wip'", True),
        ("git commit --amend", True),
        ("git commit --amend -m 'fixup'", True),
        ("git status", False),
        ("git diff --stat", False),
    ],
)
def test_commit_blocked_from_main_checkout(
    tmp_path: Path, command: str, expected: bool
):
    main_repo = _main_checkout_cwd(tmp_path)
    assert is_git_dangerous_command(command, main_repo) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git commit -m 'wip'", False),
        ("git commit --amend", False),
        ("git commit --no-verify -m 'wip'", False),
    ],
)
def test_commit_allowed_from_linked_worktree(
    tmp_path: Path, command: str, expected: bool
):
    worktree = _linked_worktree_cwd(tmp_path)
    assert is_git_dangerous_command(command, worktree) is expected


def test_commit_blocked_via_dash_capital_c_bypass_closure(tmp_path: Path):
    main_repo = tmp_path / "main-repo"
    main_repo.mkdir()
    (main_repo / ".git").mkdir()

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text(
        f"gitdir: {main_repo}/.git/worktrees/agent-1\n", encoding="utf-8"
    )

    command = f"git -C {main_repo} commit -m 'sneaky'"
    assert is_git_dangerous_command(command, worktree) is True


@pytest.mark.parametrize("flag", ["--git-dir", "--work-tree"])
def test_commit_blocked_via_git_dir_and_work_tree_bypass_closure(
    tmp_path: Path, flag: str
):
    main_repo = tmp_path / "main-repo"
    main_repo.mkdir()
    (main_repo / ".git").mkdir()

    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text(
        f"gitdir: {main_repo}/.git/worktrees/agent-1\n", encoding="utf-8"
    )

    target = f"{main_repo}/.git" if flag == "--git-dir" else str(main_repo)
    command = f"git {flag} {target} commit -m 'sneaky'"
    assert is_git_dangerous_command(command, worktree) is True


def test_commit_not_blocked_when_dash_capital_c_points_at_a_worktree(
    tmp_path: Path,
):
    worktree = _linked_worktree_cwd(tmp_path)
    command = f"git -C {worktree} commit -m 'ok'"
    assert is_git_dangerous_command(command, tmp_path) is False


def test_commit_blocked_survives_relative_dash_capital_c(tmp_path: Path):
    main_repo = _main_checkout_cwd(tmp_path)
    subdir = main_repo / "src"
    subdir.mkdir()
    command = "git -C .. commit -m 'sneaky'"
    assert is_git_dangerous_command(command, subdir) is True


# --- the agent-owned worktree relaxation ---------------------------------

# Blocked patterns that only ever touch ONE working tree — exactly the
# subcommands git_state_scope classifies WORKTREE_LOCAL. Inside an agent-owned
# worktree they stop applying; anywhere else they are unchanged. Every other
# former member (stash, tag, bisect, submodule) is pinned DENIED there by the
# shared-state tests below.
_WORKTREE_SCOPED_DENY_LIST = [
    "git reset --hard",
    "git clean -fdx",
    "git restore f.py",
    "git checkout main",
    "git switch -c x",
    "git update-index --refresh",
]


@pytest.mark.parametrize("command", _WORKTREE_SCOPED_DENY_LIST)
def test_agent_worktree_relaxes_the_worktree_scoped_deny_list(
    tmp_path: Path, command: str
):
    _main_repo, worktree = _repo_with_agent_worktree(tmp_path, "wt")
    assert is_git_dangerous_command(command, worktree) is False


# Commands whose state is shared across every worktree of the repository
# (stash stack, tag namespace) or unverified (bisect, submodule). None of them
# is relaxed anywhere, so each is denied in EVERY tier. `stash drop stash@{0}`
# pins the positional drop form alongside the bare one.
_SHARED_STATE_DENY_LIST = [
    "git stash drop",
    "git stash clear",
    "git stash drop stash@{0}",
    "git tag -f v1",
    "git tag -d v1",
    "git bisect start",
    "git submodule update --force",
]


def _every_tier(tmp_path: Path) -> list[Path | None]:
    """The four locations a command can be issued from: no cwd at all (the
    guard must fail closed), a main checkout, a linked worktree that is not
    agent-owned, and an agent-owned worktree."""
    main_repo, agent_worktree = _repo_with_agent_worktree(
        tmp_path / "agent-owned", "wt"
    )
    plain = tmp_path / "plain"
    plain.mkdir()
    return [
        None,
        main_repo,
        _linked_worktree_cwd(plain),
        agent_worktree,
    ]


@pytest.mark.parametrize("command", _SHARED_STATE_DENY_LIST)
def test_shared_state_subcommands_denied_in_every_tier(tmp_path: Path, command: str):
    # stash drop/clear and `tag -f` act on the shared stash stack and tag
    # namespace; bisect and submodule are unverified. A shared-state (or
    # unresolved) classification must never widen inside an agent-owned
    # worktree, so the relaxation covers none of them, in any tier.
    for cwd in _every_tier(tmp_path):
        assert is_git_dangerous_command(command, cwd) is True, cwd


@pytest.mark.parametrize(
    ("command", "reason_fragment"),
    [
        ("git stash drop", "shared by every worktree"),
        # The stack-destruction reason stays drop/clear's own: it names what
        # they do to the stack, not the take-back identity rule.
        ("git stash clear", "can destroy work another worktree saved onto it"),
        ("git tag -f v1", "shared by every worktree"),
        ("git tag -d v1", "shared by every worktree"),
    ],
)
def test_scope_denial_names_the_shared_state(command: str, reason_fragment: str):
    # INV-1: a denial names its reason. These name the shared stack or tag
    # namespace itself, and do so identically in every tier — checked without
    # a cwd on purpose, so the reason visibly does not depend on location.
    message = build_git_danger_block_message(command)
    assert message is not None
    assert reason_fragment in message


# The take-back denial (REQ-005) names the shared stack AND the permitted
# alternative, stated as identity-versus-position so a future shared-stack
# operation is covered by the same sentence — and it is the take-back forms'
# own reason, not drop/clear's.
_TAKE_BACK_REASON_FRAGMENTS = (
    "shared by every worktree",
    "never by position",
    "commit hash",
    "git stash apply <commit>",
)


@pytest.mark.parametrize(
    "command",
    [
        "git stash pop",
        "git stash apply",
        "git stash apply stash@{0}",
        "git stash branch take-back stash@{1}",
    ],
)
@pytest.mark.parametrize("reason_fragment", _TAKE_BACK_REASON_FRAGMENTS)
def test_take_back_denial_names_the_stack_and_the_identity_alternative(
    command: str, reason_fragment: str
):
    message = build_git_danger_block_message(command)
    assert message is not None
    assert reason_fragment in message
    assert "can destroy work another worktree saved onto it" not in message


@pytest.mark.parametrize("command", ["git stash drop", "git stash clear"])
def test_stash_stack_denial_names_pruning_as_a_human_action(command: str):
    # The spec's permission matrix requires the drop/clear denial to name
    # the shared stack "and that pruning is a human action" (REQ-005b): the
    # growth consequence is part of the reason an agent is refused, not
    # only rule-file prose.
    message = build_git_danger_block_message(command)
    assert message is not None
    assert "pruning is a human action" in message
    assert "outside the tool layer" in message


def test_an_unreadable_stash_action_denies_with_the_generic_message():
    # `git stash '' drop` is denied by the unreadable-action check, but it
    # has no scope reason: scope_denial_for cannot classify an action git
    # would reject outright, so the message falls to the generic one.
    # Deliberate (Task 38 review note, pinned here): the scope reasons name
    # facts about the shared stack, and an unreadable action names nothing.
    message = build_git_danger_block_message("git stash '' drop")
    assert message is not None
    assert "shared by every worktree" not in message
    assert "never by position" not in message


@pytest.mark.parametrize(
    ("command", "reason_fragment"),
    [
        ("git bisect start", "never verified in either direction"),
        ("git submodule update --force", "never verified in either direction"),
    ],
)
def test_unverified_denial_names_the_unverified_classification(
    command: str, reason_fragment: str
):
    # The permission matrix's bisect/submodule row (REQ-004): the denial
    # names the unverified classification, never the generic message. Both
    # members route through the same class reason — bisect because
    # DEFAULT_BLOCKED is what denies it, submodule because its checker fires
    # on force forms alone. Checked without a cwd, like the shared-state
    # reasons: the classification does not depend on location.
    message = build_git_danger_block_message(command)
    assert message is not None
    assert reason_fragment in message
    assert "destructive or irreversible" not in message


# S-02 (REQ-005): a positional take-back is denied in EVERY tier — the shared
# stack is exactly why stash earns no worktree relaxation, so no tier allows
# it. This is the flip Task 36's inverse pin waited for: that pin asserted pop
# and positional apply allowed everywhere, because the take-back boundary then
# still stopped at drop/clear.
_POSITIONAL_STASH_TAKE_BACK_DENY_LIST = [
    "git stash pop",
    "git stash apply",
    "git stash apply stash@{0}",
    "git stash branch take-back",
]


@pytest.mark.parametrize("command", _POSITIONAL_STASH_TAKE_BACK_DENY_LIST)
def test_positional_stash_take_back_denied_in_every_tier(tmp_path: Path, command: str):
    for cwd in _every_tier(tmp_path):
        assert is_git_dangerous_command(command, cwd) is True, cwd


# S-03 (REQ-005a): over-tightening would break the sanctioned recovery, so the
# identity forms and every add-only form must survive in EVERY tier too —
# including the agent-owned worktree where the recovery actually runs. A
# take-back that names its stash commit's hash removes no stack entry
# (measured), and `store` is what both measured recoveries used.
_COMMIT_NAMED_STASH_ALLOW_LIST = [
    "git stash apply 9e7e9ab",
    "git stash branch from-hash 9e7e9ab",
    "git stash push -m save",
    "git stash create",
    "git stash store 9e7e9abac52286fbd31c317a3801eed37c5e8219",
    "git stash list",
    "git stash show",
]


@pytest.mark.parametrize("command", _COMMIT_NAMED_STASH_ALLOW_LIST)
def test_commit_named_take_back_and_add_only_forms_allowed_in_every_tier(
    tmp_path: Path, command: str
):
    for cwd in _every_tier(tmp_path):
        assert is_git_dangerous_command(command, cwd) is False, cwd


@pytest.mark.parametrize("command", _WORKTREE_SCOPED_DENY_LIST)
def test_deny_list_still_applies_in_a_non_agent_linked_worktree(
    tmp_path: Path, command: str
):
    # Load-bearing counterpart to the test above: without it, an
    # implementation that relaxed inside ANY linked worktree would pass.
    assert is_git_dangerous_command(command, _linked_worktree_cwd(tmp_path)) is True


@pytest.mark.parametrize(
    "command",
    [
        "git push origin main",
        "git send-pack /r",
        "git config --list",
        "git remote add origin u",
        "git gc --aggressive",
        "git gc --prune=now",
        "git reflog expire --all",
        "git reflog delete HEAD@{1}",
        # Governed by their target, not by where they run from, so being
        # inside an agent-owned worktree grants them nothing.
        "git worktree remove -f /tmp/elsewhere",
        "git branch -D main",
    ],
)
def test_shared_state_subcommands_stay_blocked_in_an_agent_worktree(
    tmp_path: Path, command: str
):
    # A worktree shares .git/config, the object store and the reflog with the
    # main checkout, and push writes to the shared remote. None of that is
    # worktree-scoped, so "no limits inside the worktree" cannot cover it.
    _main_repo, worktree = _repo_with_agent_worktree(tmp_path, "wt")
    assert is_git_dangerous_command(command, worktree) is True


def test_agent_worktree_relaxation_follows_the_location_override(tmp_path: Path):
    # The relaxation keys on the checkout the command actually operates
    # against, in both directions.
    main_repo, worktree = _repo_with_agent_worktree(tmp_path, "wt")
    into_worktree = f"git -C {worktree} reset --hard"
    into_main = f"git -C {main_repo} reset --hard"
    assert is_git_dangerous_command(into_worktree, main_repo) is False
    assert is_git_dangerous_command(into_main, worktree) is True
    # `--no-verify` resolves the same override, so it no longer masks the
    # relaxation for the `-C` form the rule files recommend.
    assert is_git_dangerous_command(f"{into_worktree} --no-verify", main_repo) is False
    assert is_git_dangerous_command(f"{into_main} --no-verify", worktree) is True


def test_agent_worktree_relaxation_applies_from_a_subdirectory(tmp_path: Path):
    # Ownership is tested against the working-tree root owning the location,
    # not the raw location, because agents run commands from subdirectories.
    _main_repo, worktree = _repo_with_agent_worktree(tmp_path, "wt")
    subdir = worktree / "src" / "utils"
    subdir.mkdir(parents=True)
    assert is_git_dangerous_command("git clean -fdx", subdir) is False


@pytest.mark.parametrize(
    "body",
    [
        "Run `git status` first; don't skip it.",
        "Never pass --no-verify by hand.",
        "s = '''docstring'''  # §2's own cost",
    ],
)
def test_a_heredoc_body_is_data_and_never_blocks_on_its_own(
    body: str, tmp_path: Path
) -> None:
    # Measured before this: an apostrophe anywhere in the body raised
    # `ValueError: No closing quotation` inside shlex, and both entry points
    # fail closed by naming the whole command as the blocked segment -- with
    # no git command present anywhere in it.
    command = f"cat <<'EOF' > notes.md\n{body}\nEOF\n"

    assert is_git_dangerous_command(command, _main_checkout_cwd(tmp_path)) is False
    assert build_git_danger_block_message(command) is None


def test_a_command_substitution_in_an_unquoted_heredoc_body_still_blocks(
    tmp_path: Path,
) -> None:
    # An unquoted delimiter is expanded, so this really runs. Dropping the
    # body here would widen what gets through, which is the one outcome worse
    # than the friction the heredoc handling removes.
    command = "cat <<EOF > notes.md\n$(git reset --hard)\nEOF\n"

    assert is_git_dangerous_command(command, _main_checkout_cwd(tmp_path)) is True


@pytest.mark.parametrize(
    "command",
    [
        "git reset --hard",
        "cat <<'EOF' > notes.md\nprose\nEOF\ngit reset --hard",
        "cat <<'EOF' > notes.md\nprose\nEOF\n",
    ],
)
def test_a_blocked_git_command_outside_a_heredoc_is_still_refused(
    command: str, tmp_path: Path
) -> None:
    expected = "git reset --hard" in command
    assert is_git_dangerous_command(command, _main_checkout_cwd(tmp_path)) is expected


@pytest.mark.parametrize(
    "command",
    [
        "echo `git reset --hard`",
        'echo "`git reset --hard`"',
        'echo "$(git reset --hard)"',
        "x=`git clean -fd`",
        "echo $(echo $(git reset --hard))",
    ],
)
def test_a_substitution_that_runs_a_blocked_git_command_is_refused(
    command: str, tmp_path: Path
) -> None:
    # Measured before this: only the bare `$(...)` form was ever seen, and
    # only because `(` is a shlex punctuation character. Backticks split
    # nothing, and either form inside double quotes stayed one word -- so
    # three of the four shapes that really execute ran past the deny-list.
    assert is_git_dangerous_command(command, _main_checkout_cwd(tmp_path)) is True


@pytest.mark.parametrize(
    "command",
    [
        "echo '`git reset --hard`'",
        "echo '$(git reset --hard)'",
        r"echo \`git reset --hard\`",
        "echo `git status`",
    ],
)
def test_text_the_shell_never_runs_as_a_blocked_command_is_not_refused(
    command: str, tmp_path: Path
) -> None:
    # The opposite failure and no more acceptable: single quotes and a
    # backslash make a substitution literal, and `git status` is read-only.
    assert is_git_dangerous_command(command, _main_checkout_cwd(tmp_path)) is False


# --- REQ-028: the four plumbing commands are denied in every tier (Task 29) ---

_PLUMBING_COMMANDS = [
    "git update-ref refs/heads/main HEAD",
    "git commit-tree HEAD^{tree} -m 'landed without a commit'",
    "git hash-object -w --stdin",
    "git mktree",
]


@pytest.mark.parametrize("command", _PLUMBING_COMMANDS)
def test_plumbing_commands_are_denied_from_the_main_checkout(
    tmp_path: Path, command: str
):
    assert is_git_dangerous_command(command, _main_checkout_cwd(tmp_path)) is True


@pytest.mark.parametrize("command", _PLUMBING_COMMANDS)
def test_plumbing_commands_are_denied_even_in_an_agent_owned_worktree(
    tmp_path: Path, command: str
):
    # Each one moves a ref or writes an object, and both are shared no matter
    # which checkout runs the command, so the agent-worktree relaxation must
    # never reach them.
    _main_repo, worktree = _repo_with_agent_worktree(tmp_path, "wt")
    assert is_git_dangerous_command(command, worktree) is True


def test_plumbing_denial_survives_a_location_override_into_a_worktree(tmp_path: Path):
    main_repo, worktree = _repo_with_agent_worktree(tmp_path, "wt")
    command = f"git -C {worktree} update-ref refs/heads/x HEAD"
    assert is_git_dangerous_command(command, main_repo) is True


def test_plumbing_block_message_names_the_commit_block_it_defeats():
    message = build_git_danger_block_message("git update-ref refs/heads/main HEAD")
    assert message is not None
    assert "update-ref" in message
    assert "git commit" in message
    assert "Most git operations are allowed" not in message


@pytest.mark.parametrize(
    "command",
    [
        "git merge feature-x",
        "git rebase main",
        "git cherry-pick abc123",
        "git revert abc123",
        "git am some.patch",
    ],
)
def test_porcelain_commit_creators_stay_allowed(tmp_path: Path, command: str):
    # REQ-028 reaches only the four plumbing commands. These create commits as
    # their normal function and must stay allowed — pinned beside the plumbing
    # denial so a later tightening cannot silently take them. The verdict is
    # the same from an agent-owned worktree, whose relaxation equally grants
    # them nothing.
    assert is_git_dangerous_command(command, _main_checkout_cwd(tmp_path)) is False
    _main_repo, worktree = _repo_with_agent_worktree(tmp_path, "wt")
    assert is_git_dangerous_command(command, worktree) is False


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("/usr/bin/git reset --hard", True),
        ("/bin/git clean -fdx", True),
        ("/usr/local/bin/git commit -m x", True),
        ("/usr/bin/git update-ref refs/heads/main HEAD", True),
        ("/usr/bin/git status", False),
        ("/opt/git/bin/git stash list", False),
        ("sudo /usr/bin/git reset --hard", True),
    ],
)
def test_a_path_spelled_git_binary_is_classified_like_bare_git(
    tmp_path: Path, command: str, expected: bool
):
    # Measured before the fix: every True row was ALLOWED from the main
    # checkout while its bare spelling was blocked, because the head token was
    # compared to "git" literally. It is matched on its basename now.
    assert is_git_dangerous_command(command, _main_checkout_cwd(tmp_path)) is expected


def test_a_path_spelled_binary_still_resolves_the_location_override(tmp_path: Path):
    # The basename match must not disturb the override machinery: `-C` decides
    # the tier exactly as it does for the bare spelling.
    main_repo, worktree = _repo_with_agent_worktree(tmp_path, "wt")
    into_worktree = f"/usr/bin/git -C {worktree} reset --hard"
    into_main = f"/usr/bin/git -C {main_repo} reset --hard"
    assert is_git_dangerous_command(into_worktree, main_repo) is False
    assert is_git_dangerous_command(into_main, worktree) is True


@pytest.mark.parametrize(
    "command",
    [
        "git stash '' drop",
        "git stash '' clear",
        "git reflog '' delete HEAD@{0}",
        "git reflog '' expire --all",
        "git worktree '' remove --force /tmp/elsewhere",
        "git '' update-ref refs/heads/main HEAD",
        "git '' reset --hard",
    ],
)
def test_an_empty_token_cannot_defeat_a_positional_read(tmp_path: Path, command: str):
    # Measured before the fix: every row was ALLOWED because a quoted empty
    # argument sat exactly where a checker reads the action — or the
    # subcommand itself. git rejects each spelling outright (measured in a
    # throwaway repo), so failing closed here costs nothing and pins the
    # class shut the way `git branch '' -D` already is.
    assert is_git_dangerous_command(command, _main_checkout_cwd(tmp_path)) is True


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        # Both accepted by git (rc=0, measured): neither subcommand's check
        # reads a positional action, so an empty operand decides nothing.
        ("git status ''", False),
        ("git tag ''", False),
        # (The stash rows left this list: `pop` is now denied outright — its
        # checker never reads an operand, positional or empty — and an empty
        # apply operand is not a hash, so the take-back analysis fails closed
        # on it. Both covered by the stash form matrix above.)
    ],
)
def test_empty_tokens_a_positional_check_never_reads_decide_nothing(
    tmp_path: Path, command: str, expected: bool
):
    assert is_git_dangerous_command(command, _main_checkout_cwd(tmp_path)) is expected


def test_an_empty_option_value_is_not_mistaken_for_an_action_position(
    tmp_path: Path,
):
    _main_repo, worktree = _repo_with_agent_worktree(tmp_path, "wt")
    assert is_git_dangerous_command("git commit -m ''", worktree) is False


def test_a_substitution_cannot_smuggle_a_push_into_the_canonical_shape(
    tmp_path: Path,
) -> None:
    # Lifting removes the substitution's text from where it stood, so a push
    # whose branch is computed at runtime cannot read as the one authorized
    # three-token form: the branch it would name is not knowable statically.
    command = "git push -u origin HEAD:$(echo main)"

    assert is_git_dangerous_command(command, _main_checkout_cwd(tmp_path)) is True
