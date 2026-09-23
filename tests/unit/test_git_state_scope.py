"""S-01/AC-001: the guard's relaxed set is the declaration's WORKTREE_LOCAL view.

The relaxed set must not be an independently written list a comment can lie
about (the old comment claimed all ten members touch one working tree; the
stash stack and the tag namespace do not). These pins bind the guard's set to
`src/utils/git_state_scope.py`, the single place the classification lives.
"""

import pytest

from agentic_workflows.git_state_scope import (
    GIT_STATE_SCOPE,
    HOST_WIDE_HAZARDS,
    GitStateScope,
)
from agentic_workflows.git_write_guard import AGENT_WORKTREE_RELAXED_SUBCOMMANDS


@pytest.mark.parametrize(("subcommand", "scope"), sorted(GIT_STATE_SCOPE.items()))
def test_relaxed_set_membership_follows_the_declaration(
    subcommand: str, scope: GitStateScope
):
    # INV-4/AC-001: a subcommand is relaxed inside an agent-owned worktree if
    # and only if the declaration classifies it WORKTREE_LOCAL. One test per
    # declared member, not per relaxed member, so a misclassification cannot
    # hide by leaving both sides untouched.
    assert (subcommand in AGENT_WORKTREE_RELAXED_SUBCOMMANDS) is (
        scope is GitStateScope.WORKTREE_LOCAL
    )


def test_relaxed_set_is_the_derived_worktree_local_view():
    # The derivation pinned whole: the guard's set is not a second store of
    # the classification, it IS the declaration's worktree-local members.
    derived = frozenset(
        subcommand
        for subcommand, scope in GIT_STATE_SCOPE.items()
        if scope is GitStateScope.WORKTREE_LOCAL
    )
    assert derived == AGENT_WORKTREE_RELAXED_SUBCOMMANDS
    assert isinstance(AGENT_WORKTREE_RELAXED_SUBCOMMANDS, frozenset)


def test_the_three_required_categories_exist():
    # REQ-006a: three categories, not two. The host-wide one is not vacuous:
    # it names the pre-commit patch cache, which is written under the user's
    # home cache dir by EVERY committing repository on this machine.
    assert {
        GitStateScope.WORKTREE_LOCAL,
        GitStateScope.REPOSITORY_WIDE,
        GitStateScope.HOST_WIDE,
    } <= set(GitStateScope)
    assert any("pre-commit" in hazard for hazard in HOST_WIDE_HAZARDS)


def test_every_declared_member_carries_an_explicit_scope():
    # REQ-004: no member's classification may be left unstated. Ten declared
    # subcommands, each with a real category — nothing implicitly lumped in.
    assert len(GIT_STATE_SCOPE) == 10
    assert set(GIT_STATE_SCOPE.values()) <= set(GitStateScope)
