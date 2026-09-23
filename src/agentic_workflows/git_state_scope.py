"""The shared-state classification of git subcommands, declared exactly once
(REQ-006, REQ-006a, D-007).

What a git operation touches is a fact about repositories and machines, so it
is declared here — a leaf with no `src` imports of its own — and every
consumer derives from it. `git_write_guard` derives its agent-owned-worktree
relaxation from `WORKTREE_LOCAL_SUBCOMMANDS`; it never re-states the set.

The declaration classifies subcommands only — never flags or operand shapes:
whether `clean -n` differs from `clean -fdx`, `tag -f` from `tag -d`, or
`checkout <branch>` from `checkout <commit> -- <paths>` is the guard's own
checkers' business, and a member's category is the same for every flag form.
A subcommand with no entry here (e.g. `push`) is decided by the guard's other
lists, not by scope. The one operand-shape fact that lives here despite that
boundary is the stash take-back's (REQ-005, DD-001): identity-versus-position
is a fact about the shared stack itself, not about any one working tree, so
the guard's stash checker and message path delegate to
`stash_take_back_names_a_position` and `scope_denial_for` rather than
restating either.

Three categories, not two, because at least one hazard is shared beyond any
one repository:

- `WORKTREE_LOCAL` — state that exists once per working tree. Only these are
  relaxed inside an agent-owned worktree (INV-4).
- `REPOSITORY_WIDE` — one instance shared by EVERY worktree of the
  repository: the stash stack, the tag namespace.
- `HOST_WIDE` — shared by every repository on this machine, so no
  repository-scoped rule can contain it (see `HOST_WIDE_HAZARDS`).

`UNVERIFIED` is a fourth, honest state for members whose scope the grounding
could not establish in either direction (REQ-004). They are relaxed nowhere:
widening a tier from an unresolved fact is forbidden (INV-2). A later
verification flips a member to `WORKTREE_LOCAL` by editing one line here and
the derived set follows — or records the accepted limit in the rule files.
"""

import re
from enum import StrEnum


class GitStateScope(StrEnum):
    """The closed set of shared-state categories a git operation can touch."""

    WORKTREE_LOCAL = "worktree-local"
    REPOSITORY_WIDE = "repository-wide"
    HOST_WIDE = "host-wide"
    UNVERIFIED = "unverified"


# The classification itself. The comment on every member states the measured
# basis for its category and must stay true of it (REQ-002).
GIT_STATE_SCOPE: dict[str, GitStateScope] = {
    # One HEAD, one index, and one set of working files per working tree;
    # none of these reaches past the invoking checkout.
    "checkout": GitStateScope.WORKTREE_LOCAL,
    "clean": GitStateScope.WORKTREE_LOCAL,
    "reset": GitStateScope.WORKTREE_LOCAL,
    "restore": GitStateScope.WORKTREE_LOCAL,
    "switch": GitStateScope.WORKTREE_LOCAL,
    "update-index": GitStateScope.WORKTREE_LOCAL,
    # One stash stack (refs/stash) per repository — `drop`/`clear` destroy
    # entries every worktree saved onto it.
    "stash": GitStateScope.REPOSITORY_WIDE,
    # One tag namespace (refs/tags/) per repository — `tag -f`/`-d` re-point
    # or delete a name every worktree resolves identically.
    "tag": GitStateScope.REPOSITORY_WIDE,
    # refs/bisect/* was not verified to be per-worktree, so its scope is
    # unstated rather than assumed. REQ-004 disposition: removed from the
    # relaxation — the unverified claim is refs/bisect/*'s per-worktree
    # privacy, never verified and not verifiable read-only, so bisect stays
    # blocked in every tier until a human verifies it, and its denial names
    # this unresolved classification.
    "bisect": GitStateScope.UNVERIFIED,
    # Unmeasured, and moot here: this repository has no .gitmodules, so the
    # old relaxation was dead code rather than a live hazard (A-004).
    # REQ-004 disposition: removed from the relaxation on that measured
    # basis; its scope stays unstated rather than assumed.
    "submodule": GitStateScope.UNVERIFIED,
}

# The relaxation-relevant view of the declaration: exactly the members a
# linked agent-owned worktree may run freely, because their state ends at the
# working tree's own edge. Derived, never re-stated.
WORKTREE_LOCAL_SUBCOMMANDS: frozenset[str] = frozenset(
    subcommand
    for subcommand, scope in GIT_STATE_SCOPE.items()
    if scope is GitStateScope.WORKTREE_LOCAL
)

# Hazards shared across every repository on this machine. No git subcommand
# names them, so they have no members in GIT_STATE_SCOPE — the category
# exists because a worktree-vs-repository binary cannot represent them.
HOST_WIDE_HAZARDS: tuple[str, ...] = (
    # pre-commit's set-aside patch cache: written under
    # ~/.cache/pre-commit/patch<ts>-<pid> by any concurrently committing
    # repository on the machine, with no repository, branch, or worktree
    # attribution in the entry itself.
    "pre-commit patch cache (~/.cache/pre-commit/patch<ts>-<pid>)",
)

# Reasons that name why a dangerous declared member is denied (INV-1): a
# repository-wide member's reason names the shared state itself; an
# UNVERIFIED member's names the unresolved classification, because no shared
# mechanism was ever measured to name. The guard consults this table only for
# a segment its own rules have already judged dangerous — a fired checker, or
# (for a checker-less member) DEFAULT_BLOCKED_GIT_SUBCOMMANDS membership — so
# a message here can never fire for a command any tier allows.
STASH_STACK_DENIAL = (
    "Blocked: the stash stack is one list shared by every worktree in this "
    "repository — `git stash drop`/`git stash clear` can destroy work another "
    "worktree saved onto it, and that pruning is a human action performed "
    "outside the tool layer (see .agents/rules/block-git-mutations.md)."
)
TAG_NAMESPACE_DENIAL = (
    "Blocked: a tag is one name in a namespace shared by every worktree in "
    "this repository — `git tag -f`/`git tag -d` re-point or delete a name "
    "other worktrees and builds may rely on (see "
    ".agents/rules/block-git-mutations.md)."
)
UNVERIFIED_CLASSIFICATION_DENIAL = (
    "Blocked: this subcommand's scope was never verified in either direction "
    "(UNVERIFIED in src/utils/git_state_scope.py), so it earns no worktree "
    "relaxation and this denial stands in every tier until its scope is "
    "verified worktree-local (see .agents/rules/block-git-mutations.md)."
)
SCOPE_DENIALS: dict[str, str] = {
    "stash": STASH_STACK_DENIAL,
    "tag": TAG_NAMESPACE_DENIAL,
    # bisect is denied outright by the guard's DEFAULT_BLOCKED list in every
    # tier; submodule only ever denies its force forms (its checker fires on
    # force flags alone, and non-force submodule stays allowed by default).
    # Both route here (REQ-004) so the denial names the unresolved
    # classification instead of a shared mechanism nobody measured.
    "bisect": UNVERIFIED_CLASSIFICATION_DENIAL,
    "submodule": UNVERIFIED_CLASSIFICATION_DENIAL,
}

# The stash subcommands that take an entry back OFF the shared stack. The
# add-only forms (`push`, `create`, `store` — REQ-005a, `store` being what
# both measured recoveries used) and the read-only ones (`list`, `show`) are
# absent on purpose: they destroy nothing.
STASH_TAKE_BACK_ACTIONS = frozenset({"apply", "branch", "pop"})

# The one operand spelling that names a stash COMMIT itself — identity,
# race-free — rather than a position on the shared stack. Abbreviated is
# enough: git resolves it to the same immutable object.
STASH_COMMIT_HASH = re.compile(r"[0-9a-fA-F]{7,64}")


def stash_take_back_names_a_position(args: list[str]) -> bool:
    """True when a stash invocation takes an entry back off the shared stack
    without naming that entry's commit hash. `pop` always qualifies: it
    removes a stack entry by construction and rejects a hash operand outright
    (measured), so no pop spelling names an identity. `apply` and `branch`
    qualify when their stash operand is absent — git then reads the stack top
    — or names a stack position (`stash@{n}`, `refs/stash`); flags and a `--`
    separator never hide the operand from this read. `branch`'s first operand
    is the branch it creates, not the stash target."""
    if not args or args[0] not in STASH_TAKE_BACK_ACTIONS:
        return False
    if args[0] == "pop":
        return True
    operands = [token for token in args[1:] if not token.startswith("-")]
    if args[0] == "branch" and operands:
        operands = operands[1:]
    return not (operands and STASH_COMMIT_HASH.fullmatch(operands[0]))


# The take-back's own denial (REQ-005), distinct from drop/clear's: those
# destroy an entry whatever they name, while a positional take-back destroys
# WHICHEVER entry the position holds at the moment of taking — the race both
# measured work-destruction incidents rode on. The identity rule is stated as
# identity-versus-position on a shared stack, not as a stash fact, so any
# future shared-stack operation is covered by the same sentence.
STASH_TAKE_BACK_DENIAL = (
    "Blocked: taking an entry back off a shared stack is allowed only when "
    "the command names that entry's commit hash (identity), never by position "
    "— the stash stack is one list shared by every worktree in this "
    "repository, and a positional take-back (`git stash pop`, `git stash "
    "apply` without a hash operand, `git stash branch` given a stack "
    "reference) consumes whatever was saved there most recently, whoever "
    "saved it: both measured work-destruction incidents were an operand-less "
    "`git stash pop` that consumed a different worktree's uncommitted work. "
    "Name the stash commit instead — `git stash apply <commit>` or "
    "`git stash branch <name> <commit>` removes nothing from the stack, "
    "measured, while `git stash pop` cannot accept a hash at all — with the "
    "hash captured race-free when the stash is created (see "
    ".agents/rules/block-git-mutations.md)."
)


def scope_denial_for(subcommand: str, args: list[str]) -> str | None:
    """The denial a dangerous declared member is refused with (INV-1), chosen
    by what THIS invocation targets when one member carries more than one
    reason: stash denies `drop`/`clear` with the stack-destruction reason and
    a positional take-back with the identity reason. Add-only and read-only
    stash forms get None here — exactly the guard checker's verdict for them —
    so the message can never disagree with the guard."""
    if subcommand != "stash":
        return SCOPE_DENIALS.get(subcommand)
    if stash_take_back_names_a_position(args):
        return STASH_TAKE_BACK_DENIAL
    if bool(args) and args[0] in {"clear", "drop"}:
        return STASH_STACK_DENIAL
    return None
