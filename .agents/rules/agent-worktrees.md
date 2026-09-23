---
trigger: always_on
---

# Agent-Owned Worktrees

Recorded 2026-08-03 alongside the git-mutation guard change that finally lets
agents clean up after themselves. Before this, `git worktree remove --force`
and `git branch -D` were hard-blocked everywhere, and the parallel-SDD
workflow told agents to keep every worktree until a human typed "merged" or
"abandon" — a run that ended any other way left its worktree behind forever.
`.agents/rules/block-git-mutations.md` mirrors the same guard in prose but is
deliberately excluded from `.claude/rules/` auto-load (see
`.agents/rules/README.md`) on the reasoning that a hook enforces a *prohibition* whether or
not an agent has read it. That reasoning does not cover a *permission*: an
agent that never reads this file will keep escalating a dirty worktree to a
human because nothing tells it force-removal is now allowed. This file is
that statement, and it is auto-loaded specifically so the permission below is
usable in practice.

## The agent-owned root

A path is an **agent-owned worktree** iff, resolved to an absolute
normalized path, its parent is exactly `<main checkout>/.agents/worktrees`.
Direct children only — `.agents/worktrees/x/y` does not qualify. Neither does
`.claude/worktrees/`: that directory belongs to the Claude Code harness's own
worktree tool, is never created through a Bash `git` command this guard can
see, and is not adopted as a second root — granting it the same powers would
hand force-removal over directories this repo does not manage.

## Nothing serializes two actors in one worktree

The ownership above is a permission to work in isolation, not
exclusivity. This limit is stated here — in the always-loaded file an
actor reads before touching any tree — because this is where the
acting party has to meet it. Nothing in the guard, the hooks, or this
repository's tooling serializes a reviewer, or any second actor,
against an implementer holding uncommitted work in the same worktree.
While both write that tree they destroy each other's state silently:
no lock, no warning, no denial from either direction.

The loss mode has no undo. Destroyed uncommitted work leaves no
git-native record: the reflog tracks commit pointers — where HEAD and
branch refs have moved — and never held the uncommitted content, so
once the work is overwritten or discarded there is nothing to walk
back to. Do not treat the reflog as a safety net here; it can offer
nothing for content that was never committed. Unstaged work — content
never added to the index — truly leaves nothing. Once-staged work is
the one nuance: discarding it may leave an unlisted, unattributed
object that only the forensic `git fsck --unreachable` finds, and only
until gc prunes it — never a listed, attributed, recoverable record.
The only identity that
survives a collision is one captured before it — a stash hash recorded
at save time, as the stash section below prescribes — and only for
work that was stashed.

This is an accepted limit, stated and deliberately not enforced: no
serialization mechanism is required or attempted by this change, and
prevention is by convention alone — one writer per worktree, and a
second actor asks or reads elsewhere before writing into a tree
another actor may hold with uncommitted work.

## A commit killed by a tool timeout mid-set-aside silently discards unstaged edits

When `git commit` runs the commit gate, pre-commit sets the working
tree's unstaged changes aside so hooks see only the staged content, and
restores them when the hooks finish. A commit killed by a tool timeout
mid-set-aside never reaches that restore: the unstaged edits are
discarded, and `git status` afterwards reports the file unmodified —
`git diff` and a source read agree — while the only surviving copy of
the lost work sits outside the repository, in the set-aside cache
below. That is a different loss from the collision above: here the
work survives, but unattributed and outside any git object store.
Staged work survives — the index is both what hooks see and what the
commit carries. The convention that avoids the loss entirely: stage
everything a commit is meant to carry before issuing the commit.

The set-aside cache is `~/.cache/pre-commit/patch<ts>-<pid>` (or
`$PRE_COMMIT_HOME` when set): machine-wide, shared by every repository
on this machine, and its entries carry no repository, branch, or
worktree attribution — a filename of an epoch timestamp and a PID. A
recovering agent cannot reliably identify its own entry, so recovery
is not merely awkward but potentially wrong — applying another
repository's patch is a real outcome — and it is not prescribed as
safe. There is no marker beyond
the cache itself: pre-commit keeps no marker of which patch, if any,
was never restored. Before any manual application, a human must check
the entry's timestamps against when the loss happened and the patch
content against the lost file's expected diff. Full mechanics:
`.agents/rules/block-git-mutations.md`'s set-aside section.

## A clean tree does not prove clean bytecode — clear `__pycache__`

Reverting a module to its earlier content can leave a stale `.pyc` in
`__pycache__` that outlives the revert, and then `git status`, `git diff`,
and a source read all agree the tree is clean while the interpreter still
executes the reverted-away code. Measured on this machine's Python 3.12:
importlib validates a cached `.pyc` against the source's mtime in whole
seconds and its byte size, so a revert that restores a same-length source
within the same whole-second mtime the mutated file was last imported under
passes the check, and every later run imports the mutated bytecode. The
signal, when it surfaces, is a wall of failures in files the change never
touched, which reads as a broken branch rather than as stale bytecode.
Deleting a source outright is not the hazard here: this Python refuses an
orphaned `__pycache__` entry whose source is gone (`ModuleNotFoundError`).

No cheap detection exists — the stale entry's cached mtime and size match
the reverted source (that is why it loads), so it is indistinguishable from
a valid one without recompiling every module, which defeats the cache. The
check an agent CAN run is the clear, and the time to run it is after any
revert of a source file — `git restore`/`git checkout`, a mutation-restore,
`git stash apply` — and before trusting a green run that depends on the
reverted file:

```bash
find . -name '__pycache__' -type d -prune -exec rm -rf {} +
```

## `git worktree add` is now restricted, not unconditionally allowed

Before this change, `git worktree add <path>` succeeded anywhere. Now its
`<path>` operand must itself resolve to an agent-owned location, or the
command is blocked outright: a worktree created outside
`.agents/worktrees/` would lose every permission this file grants, and the
block has no relaxation. Create worktrees with an
absolute path (`git worktree add <main-checkout-absolute-path>/.agents/worktrees/<name>
...`) or `git -C <main-checkout-path> worktree add .agents/worktrees/<name>
...` — a bare relative path resolves against the session's own `cwd`, so it
only succeeds when that happens to already be the main checkout. See
"`cwd` is a snapshot, not tracked shell state" below for why, and
`.agents/rules/block-git-mutations.md`'s matching sections for the full
mechanics of `-C`/`--git-dir`/`--work-tree`.

## Worktree creation is script-only; the per-run cap is config-owned

Never create, re-sync, or remove an agent worktree with a hand-issued `git
worktree add`, `git worktree remove`, or branch-reset command — even in the
authorized shapes above. The one legal route for agents is
`.agents/scripts/worktree_acquire.py` (`acquire`/`status`/`release`, run via
`python3 .agents/scripts/worktree_acquire.py ...`; `acquire` and `release`
require `--run <branch>` naming the calling run), which leases each
worktree to exactly one run, refuses to remove or re-sync a worktree whose
uncommitted work is not committed to its holder's branch, and releases a
slot only to the run that owns the lease — never discarding work. There is
no timer: a live holder is never auto-reclaimed; freeing a slot is the
owning run's explicit, durability-gated release (a resumed run reclaims its
own stale holders the same way, via status → release → acquire). A
hand-issued command bypasses the lease ledger and the durability refusal,
and is prohibited for that reason, not merely discouraged.

The cap those commands enforce is **N: the maximum number of agent
worktrees leased to one run under `.agents/worktrees/` at any moment**
(other runs' worktrees — leased or not — never count against your run and
are never touched by it; the run's single integration worktree is exempt).
The `--run` identity is self-asserted at this trust level: the cap and the
lease ledger fence agents against one another's worktrees, and same-user
tampering with that identity is out of contract per the spec's
authorization matrix.
N's single machine-readable owner is `.agents/config.toml`
(`[worktrees] max_concurrent`), read by the
acquire script and the Claude Code hook backstop alike through
`agentic_workflows/worktree_capacity` — this file deliberately restates no number,
because a second store is how caps rot. Agents never change N. The hook
backstop runs in Claude Code only; harnesses without PreToolUse hooks keep
the script's own refusals but lose the mechanical backstop against a raw
command (the parallel-subagent-driven-development skill's
`references/zcode-compat.md` records that accepted loss).

Removal itself is **automatic, never a human gate**: a worktree is
released by the script the moment its holder's work has merged (or, for a
run's integration worktree, once the run's pull request is open). What the
old human confirmation protected is protected mechanically instead — the
durability invariant above: commit-or-merge is verified before removal
*and* before a reuse that re-syncs the tree to another tip, and the remove
path refuses otherwise.

## What's unrestricted inside — scoped to the session's own `cwd`

<!-- BEGIN GENERATED: git-state-scope -->
<!-- Rendered from agentic_workflows/git_state_scope.py by scripts/render_git_state_scope_block.py; regenerate with `python3 scripts/render_git_state_scope_block.py --apply` — never hand-edit this block. tests/unit/test_git_state_scope_block.py fails on any drift from the declaration. -->

What each `git` subcommand touches, declared once in code. The classification
covers subcommands only — never flags or operand shapes — and a subcommand with
no entry below is decided by the guard's other lists.

- worktree-local — state that exists once per working tree; relaxed inside an
  agent-owned worktree, and nothing else is: checkout, clean, reset, restore,
  switch, update-index
- repository-wide — one instance shared by every worktree of this repository,
  so one worktree's command can destroy another worktree's: stash, tag
- unverified — scope not established in either direction; relaxed nowhere, so
  every tier decides each member by the guard's other lists alone: bisect,
  submodule
- host-wide — shared by every repository on this machine, so no repository-
  scoped rule can contain it: pre-commit patch cache (~/.cache/pre-
  commit/patch<ts>-<pid>)

The guard's agent-owned-worktree relaxation is derived from this declaration,
never re-stated: it is exactly the worktree-local members above.
<!-- END GENERATED: git-state-scope -->

Once a session's working directory resolves inside an agent-owned worktree,
exactly the subcommands the block above classifies as worktree-local — and
nothing else — are permitted regardless of flags; every subcommand it
classifies repository-wide or unverified gets no relaxation from this tier,
and what then happens to each is decided by the guard's other lists, not by
the classification alone — `git bisect` is blocked in every tier because its
scope was never verified, while `git submodule` is denied only on its force
forms, each documented in `.agents/rules/block-git-mutations.md`. The block
is rendered from
`agentic_workflows/git_state_scope.py`, and
`tests/unit/test_git_state_scope_block.py` fails on any drift, so this file
never restates the classification in prose — a second, untested store is how
the old hand-written list rotted. (Recorded 2026-08-28: the ten-subcommand
relaxation this section used to enumerate did not survive its own derivation
— the entries that measured repository-wide or unverified were removed from
the relaxation, deliberately.)

Everything already allowed anywhere (`add` for an agent-owned target,
`commit`, `merge`, `rebase`, non-force `worktree remove`, and so on) is
unaffected by any of this.

## The shared stash stack: it grows until a human prunes it — capture the hash at save time

`stash` is classified repository-wide above because the stack is one list
shared by every worktree. What that means for agents: the only stash
commands that touch the stack without destroying anything are the additive
ones — `git stash push`, `git stash create`, `git stash store` — plus the
read-only `list`/`show`, and take-backs that name an explicit commit hash.
Every positional take-back is denied in every tier: `git stash pop` in
every spelling, `git stash apply`/`git stash branch` given a stack
position (`stash@{n}`, `refs/stash`, bare `stash`) or no stash operand,
and `git stash drop`/`git stash clear` outright. With every positional
take-back denied, no agent-issued command can shrink the stack: it grows
until a human prunes it, and that pruning is a human action performed
outside the tool layer — a known consequence of the identity rule, not a
surprise.

Because any worktree can save onto the shared stack at any moment, a
position is never a safe name: another agent's save between this agent's
save and a later `git stash list` renumbers every entry. The race-free
identity is the entry's commit hash, and the only moment to capture it is
the save itself — `git stash create` prints the hash on stdout and
modifies nothing (not the stack, not the working tree), and `git stash
store` then adds exactly that commit:

```bash
HASH=$(git stash create "wip: describe the work")    # prints the hash; saves nothing
git stash store -m "wip: describe the work" "$HASH"  # adds that exact commit to the stack
```

`git stash push` saves too, but prints no hash — saving with `push` alone
leaves no identity to recover with. Record the hash where the next session
will find it; recovery is then `git stash apply <hash>` (or `git stash
branch <name> <hash>`), which removes nothing from the stack. Full
mechanics: `.agents/rules/block-git-mutations.md`'s stash section.

## Force-removal and force-delete — gated by target, not by where you stand

`git worktree remove --force`/`-f` and `git branch -D`/`--delete --force`
are **not** scoped to the session's `cwd` like the list above. Each is
authorized by its own *target* — the `<path>` operand for removal, every
branch-name operand for deletion:

- `git branch -D <name>` is authorized as long as every named branch starts
  `sdd/` or `plan/` — see "The `sdd/`/`plan/` carve-out" below. A branch
  name is never a filesystem path, so this one genuinely runs from
  anywhere, unaffected by `cwd`.
- `git worktree remove --force .agents/worktrees/<name>` is authorized as
  long as its `<path>` operand *resolves* to an agent-owned worktree — but
  a relative operand needs a base to resolve against first:

  ```bash
  git worktree remove --force .agents/worktrees/agentwt                      # cwd = main checkout     -> allowed
  git worktree remove --force .agents/worktrees/agentwt                      # cwd = an agent worktree -> blocked
  git -C <main-checkout-path> worktree remove --force .agents/worktrees/agentwt   # any cwd inside the repo -> allowed
  ```

  A bare relative operand resolves against the session's own `cwd`, so the
  identical string is authorized from one `cwd` and blocked from another —
  the *target* still decides, but the target a relative operand names
  depends on what it resolves against. Two forms fix that: **an absolute
  path**, or **`-C <dir>` plus a path relative to `<dir>`** — the latter
  now works for `worktree add`/`worktree remove --force` the same way it
  already does for the checks under "`cwd` is a snapshot" below.
  `--git-dir`/`--work-tree` do not help here — neither moves the base a
  relative operand resolves against.

  Both of those two forms work from anywhere **inside this repository**,
  not literally anywhere: `-C` moves the resolution base for the operand,
  but not the anchor that decides which checkout counts as "the main
  checkout" for the ownership test — that anchor always follows the
  session's own actual working directory, never the `-C` value, precisely
  so a command can't aim the ownership test at some other repository's
  `.agents/worktrees`. A shell standing outside this repository entirely
  therefore still fails closed no matter how the path is written.

This has to be target-gated rather than cwd-scoped in the first place: git
itself refuses to remove the worktree you are currently standing in, so a
cwd-scoped rule would describe an operation that can never happen — exactly
the shape of the cleanup this rule exists to enable (removing a *finished*
worktree from outside it, e.g. from the main checkout at the parallel-SDD
workflow's automatic post-merge release or its Step 11 integration-worktree
release).

## `cwd` is a snapshot, not tracked shell state

The `cwd`-scoped relaxation above is keyed on the shell's working directory
*before* the command runs — a `cd` inside the same command has not
happened yet from the guard's point of view and changes nothing.

- **In tool environments with an explicit per-command working-directory
  parameter:** Set that parameter directly to the worktree path (e.g.
  `cwd: ".agents/worktrees/<name>"`) and run clean git subcommands (`git
  status`, `git add .`, `git commit -m "..."`). Never embed `-C <worktree-path>`
  in the command itself: dynamic path arguments break prefix-matching
  auto-approval and prompt for manual confirmation on every single command.
- **In CLI environments without a per-command working-directory parameter
  (like Claude Code Bash tool calls):**
  Use `git -C <worktree-path> ...`, the reliable form that does not depend on shell state persisting between tool calls — proven for every location-based check in the guard, `--no-verify` included. Full mechanics and worked examples: see `.agents/rules/block-git-mutations.md`'s matching section.

## Still blocked everywhere, including inside an agent-owned worktree

`send-pack`, `config`, `remote` writes, `gc --aggressive`/`gc --prune=...`,
and `reflog expire`/`reflog delete` stay blocked no matter where the
session's working directory is. A worktree shares `.git/config`, the object
store, and the reflog with the main checkout — none of that is scoped to
one working tree, so "no limits inside the worktree" cannot cover it.
Widening this list to match the relaxed one above would let an agent
working in an isolated sandbox still corrupt shared repo state.

The sharing runs deeper than the command surface, and its sharpest
instance is invisible from the directory itself: `.git/config` sets
`core.hooksPath` to an absolute path into the main checkout's `.git/hooks`,
so **every worktree resolves its hooks from that one shared directory**,
and one write there disables the commit gate for all of them at once — not
only the worktree the write was issued from. The defense is a path-class
refusal on both tool surfaces, stated per surface: the file-edit route
refuses every path at or below a `.git` entry (a worktree's own pointer
file included) plus the plan-run authorization records, and the Bash route
refuses the write shapes a command names in its own operands — while
interpreter-mediated Bash writes (`python -c`, a script handed to an
interpreter, a `bash -c`/`eval` body) remain open, stated open.
`block-git-mutations.md`'s `git config` section carries the full
two-surface statement; the ownership-anchor bullet under "Known gaps"
below applies it to the pointer file.

`push` is not on this list because it was never flatly blocked in the first
place: exactly one shape — `git push -u origin HEAD:<branch>` — can be
authorized, and only when the branch is not `main`, is recorded as owned by
an active run, and the pushed commit matches that run's verify-status and
secret-scan-clean SHAs. Every other shape is denied. **This authorization
chain is unchanged by the agent-owned-worktree tier** — being inside one
neither relaxes nor tightens it, and the parallel-SDD workflow's own Step 10
push relies on exactly this staying true. Full mechanics:
`.agents/rules/block-git-mutations.md`'s push section.

`--no-verify` and `git commit` keep their **existing, broader** predicate —
any linked worktree, not only an agent-owned one
(`block-git-mutations.md`'s own `--no-verify` and `git commit` sections).
Nothing here narrows either of those; both were already permitted in every
linked worktree before this change and stay permitted the same way. Do not
conflate the two predicates: "agent-owned worktree" is strictly narrower than
"any linked worktree."

## The `sdd/`/`plan/` carve-out

`git branch -D <name>` is permitted only when every operand starts with
`sdd/` or `plan/` — the two branch-name prefixes the parallel-SDD workflow
owns. Force-deleting one of those is that workflow's own designed cleanup;
force-deleting anything else destroys someone else's work.

## Known gaps

Path-based ownership is a guardrail against mistakes and against the
enumerated git commands above. It is **not** a security boundary against an
agent that can run arbitrary Bash:

- `bash -c "git worktree remove -f /anything"` is invisible to this guard:
  `strip_shell_wrappers` does not strip `bash`/`sh`, and the quoted body is a
  single token. This gap predates this change; letting forced removal
  through for agent-owned paths makes it more valuable to an attacker who
  can already run arbitrary Bash, not newly unsafe.
- **The ownership anchor is no longer rewritable through the tool layer —
  closed per surface, with one stated residual.** A worktree's `.git`
  pointer file is an ordinary writable file, and rewriting its `gitdir:`
  line re-points the root every ownership decision is anchored on; this
  entry recorded that as an open gap. The write is now refused on **both**
  surfaces where the route can be decided, each closure naming its
  surface. The **file-edit** route (`block_git_internals_edit.py`) refuses
  every path at or below a `.git` entry — the pointer file is a *file*
  named `.git`, reachable by no filename rule, so the guard is a path
  class, and the class is not anchored to this repository, so a wholly
  fabricated directory with its own hand-written `.git` file is refused
  the same way. The **Bash** route (`block_protected_path_write.py`)
  refuses the same class when the command names the path in its own
  operands — redirects, heredocs, `tee`, `sed -i`, `cp`/`mv`/`dd
  of=`/`install` destinations, `ln`. Stated open on the Bash route only:
  an interpreter writing through its own runtime (`python -c`, a script
  handed to an interpreter, a `bash -c`/`eval` body) is invisible to an
  operand recognizer —
  the same route the orchestration's own legitimate record writes travel —
  so the file-edit refusal does not cover it, and no statement here may
  read as if it did. This remains the mirror image of the `worktree move`
  gap below: that one relabels a *target*; this one redirected the *root*
  the target is checked against.
- `git worktree move <human-worktree> .agents/worktrees/pwned` relabels a
  human's own worktree as agent-owned by path alone. A plain `mv` of the
  directory achieves the identical relabeling with no git subcommand at
  all — its operands name no protected path, so neither write guard sees
  it. Where that route once also leaned on a hand-edited `.git` file, that
  leg is now refused on both surfaces (see the ownership-anchor bullet
  above). Restricting `worktree move`'s destination operand is
  the natural follow-up and is not part of this change.
- `sdd/` and `plan/` are agent-writable branch namespaces. A human branch
  that happens to use either prefix is force-deletable under this rule the
  same as an agent's own.
