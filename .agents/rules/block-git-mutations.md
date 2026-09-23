---
trigger: always_on
---

# Block Git Mutations

Mirror `.agents/hooks/block_git_mutations.py` behavior in passive rule form.
This is a deny-list: most git commands are allowed; a specific set of
destructive/irreversible patterns is blocked.

## A command the guard cannot parse is refused, not allowed

The guard tokenizes each command before inspecting it, so a command whose
quoting cannot be resolved — a quote opened and never closed, or a trailing
backslash — is refused, not allowed, and is never evaluated against any
pattern in this file. The refusal says exactly that: no git rule was
consulted and no blocked pattern is named. The command's text is
deliberately not echoed back, because it is arbitrary shell text that can
carry a credential and the caller already knows what it ran. When a command
is refused this way and invokes no git operation, write its body to a file
with the file-writing tool and run that file instead of embedding it inline.

## Agent-owned worktrees: a third relaxation tier

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

Two location-based relaxations already exist below: the main checkout (the
base rules), and any linked worktree, which relaxes `--no-verify` and
`git commit` only (via `_cwd_is_linked_worktree` — see their own sections
further down). A third, narrower tier sits on top of those: an
**agent-owned worktree** is a direct child of
`<main checkout>/.agents/worktrees/`. Inside one, exactly the subcommands
the block above classifies as worktree-local are fully unblocked regardless
of flags; every subcommand it classifies repository-wide or unverified keeps
exactly the behavior documented in the sections below, in this tier too.
Alongside them, `git worktree remove --force` and `git branch -D` relax as
well, each gated on its own *target* (the `<path>` operand, or every
branch-name operand) rather than on where the command runs from. `branch -D`
genuinely runs from anywhere, since a branch name is never a filesystem path;
`worktree remove --force`'s `<path>` operand needs a base to resolve
against when written relatively, and an absolute path or `-C <dir>` (but
not `--git-dir`/`--work-tree`) supplies one — see its own bullet under
"Blocked patterns" below for the worked example and mechanics. Outside an
agent-owned worktree the whole tier drops away: nothing here changes what
happens in the main checkout or in a non-agent-owned linked worktree.

The worktree-local check (the members the block above classifies
worktree-local) resolves
`-C`/`--git-dir`/`--work-tree` the same way `git commit`'s linked-worktree
check already does (see that section below): authorization follows the
*effective* checkout location, not the literal `cwd`, in both directions.
`git -C .agents/worktrees/x reset --hard` run from the main checkout is
authorized; `git -C <main-checkout> reset --hard` run with the session's own
`cwd` inside an agent-owned worktree is still blocked, because the effective
location it resolves to is the main checkout, not the worktree — the same
bypass `git commit`'s `-C` handling already closes, applied to this tier.

`--no-verify` and `git commit` are untouched by this tier: they keep their
existing, broader "any linked worktree" predicate. Do not conflate the two —
an agent-owned worktree is strictly narrower than "any linked worktree."

The full rule — the exact root-directory test, the honest "guardrail, not a
security boundary" framing, and its known gaps — lives in
`.agents/rules/agent-worktrees.md`. Unlike this file, that one **is**
projected into `.claude/rules/` and auto-loaded into every session (this
file is deliberately excluded — see `.agents/rules/README.md`'s "Claude Code
projection" section): a new *permission* only changes behavior if an agent
actually reads it, unlike a prohibition a live hook enforces regardless.

## `cwd` is a snapshot, not tracked shell state

Every location-based relaxation in this file — `--no-verify`, `git commit`
from a linked worktree, and the whole agent-owned-worktree tier above — is
keyed on one `cwd` value: the shell's working directory *before* the
command runs, exactly as `PreToolUse` reports it. This is a deliberate
design point, not a bug: the guard does not model `cd`. A `cd` inside the
very command being evaluated has not happened yet from the guard's point of
view, so it changes nothing — this is the mistake every agent hits first:

```bash
cd .agents/worktrees/my-group && git reset --hard    # BLOCKED — still
                                                       # evaluated against
                                                       # the pre-command cwd
```

Two forms work instead. Prefer the first — it does not depend on any shell
state persisting between tool calls:

```bash
git -C .agents/worktrees/my-group reset --hard        # recommended: works
                                                        # regardless of cwd
```

```bash
cd .agents/worktrees/my-group   # one call
git reset --hard                # a separate, later call — now the reported
                                 # cwd really is the worktree
```

The second form only works when the session's actual working directory
persists between the two calls.

**`-C` is proven for `--no-verify` too, settled, not a work in progress.**
`--no-verify` and `git commit` now share one predicate for resolving the
effective checkout location — the same `-C`/`--git-dir`/`--work-tree`
resolution `git commit`'s own check has always used (see that section
below) — so the two cannot drift apart from each other again. Measured
directly against the guard:

```bash
git -C <linked worktree> commit --no-verify -m x   # cwd = main checkout -> allowed
git -C <main checkout>   commit --no-verify -m x   # cwd = worktree      -> blocked
```

The second line is the one that matters: aiming `-C` at the main checkout
while your session's own `cwd` happens to be inside a worktree does **not**
slip `--no-verify` through — the effective location it resolves to is the
main checkout, and the block still applies there. `-C <worktree-path>` is
the recommended idiom for every location-based check in this file,
`--no-verify` included.

## `-C`, `--git-dir`, and `--work-tree` resolve identically — what differs is what they name

All three options are resolved by the same code path — there is no
per-flag exception, and this resolution logic predates this whole change;
it has always worked this way. What differs is what *kind* of path each
option names, and which working tree ends up owning it once the guard
walks up from there looking for the nearest `.git` entry:

| What the option names | Result |
| --- | --- |
| A work tree — `-C <worktree>`, `--work-tree=<worktree>` | Lands inside it — the relaxation applies |
| A git directory — `--git-dir=<main>/.git/worktrees/<name>` | Walks up to the main checkout — fails closed |
| A worktree's own `.git` file — `--git-dir=<worktree>/.git` | Lands inside that worktree — the relaxation applies |

The middle row is correct behavior, not a limitation to work around:
pointing `--git-dir` at the internal administrative directory a linked
worktree's metadata lives under (inside the main checkout's own
`.git/worktrees/`) walks back up into the main checkout — the same result
as never giving the flag at all, because that administrative directory is
not itself a working tree. To reach a worktree, name the worktree itself —
with `-C`, `--work-tree`, or `--git-dir=<worktree>/.git` (its own `.git`
file, not the main checkout's internal copy of its metadata) — not the
metadata directory backing it.

This table explains resolution of the *checkout location* used by
`--no-verify`, `git commit`, and the relaxed-subcommand tier above. A
`worktree add`/`worktree remove --force` `<path>` *operand* is a related
but separate concern — see the worked example under "Blocked patterns"
below for how `-C` interacts with that operand specifically, and the
important "anywhere inside the repository, not anywhere" qualifier that
applies to both.

## Always blocked, regardless of flags

- `git send-pack` (the plumbing command underneath `push`; writes refs/objects
  to a remote — stays fully blocked with no exception, unlike `push` itself,
  see "`git push`: blocked except the one canonical branch/PR-workflow form"
  below)
- `git config`, unconditionally, including read-only forms like `--get`/
  `--list`/`--global` — see "`git config` is fully blocked, both via Bash
  and via direct file edits" below.
- `git commit-tree`, `git hash-object`, `git mktree`, and `git update-ref`
  (the plumbing commands that write objects or move refs directly) are
  denied in every tier, an agent-owned worktree included: together they
  land a commit and repoint a branch without the `git commit` block ever
  running — see the `git commit` section below.

`git checkout` (ref switch, path-based discard, `-b` create+switch, detached
HEAD), `git switch`, and `git update-index` were on this list too until the
agent-owned-worktree tier above began carving out the subcommands the
generated block there classifies as worktree-local. `git bisect` was carved
out by that tier as well and is back on this list in every tier since its
scope came back unverified — the block's unverified entries are relaxed
nowhere. Outside an agent-owned worktree everything on this list remains
blocked exactly as before. `send-pack` and
`config` are not the only subcommands with no location-based exception —
`reflog expire`/`delete`, `gc --aggressive`/`--prune`, and blocked `remote`
writes (below) have none either; they simply belong to a different section
because each is a flag-gated *pattern* rather than a subcommand blocked in
full regardless of flags, which is what this section's heading describes.

## Blocked patterns (subcommand otherwise allowed)

Every pattern below still applies exactly as written in the main checkout
and in a non-agent-owned linked worktree. Inside an agent-owned worktree, a
pattern whose subcommand the generated block in "Agent-owned worktrees: a
third relaxation tier" above classifies as worktree-local is fully
unblocked regardless of the flag conditions described here; every other
subcommand below stays blocked there exactly as written. `branch -D` and
`worktree remove --force` relax too, but by a different mechanism — see
their own bullets below.

- `git reset --hard` (bare `reset`, `reset <path>`, `reset --soft`/`--mixed`
  stay allowed)
- Force-flag family: `git branch -D` / `--delete --force`, `git tag -f`/
  `--force`, `git restore` on a path (see below), `git submodule ... --force`,
  `git worktree remove --force`/`-f`
  - Exceptions: `git add -f` and `git rebase -f`/`--force-rebase` stay allowed.
  - `git branch -D` is additionally allowed when every branch-name operand
    starts with `sdd/` or `plan/` — the two prefixes the parallel-SDD
    workflow owns — regardless of where the command runs from. A mixed
    invocation naming even one non-`sdd/`/`plan/` branch is still blocked.
  - `git worktree remove --force`/`-f` is additionally allowed when its
    `<path>` operand resolves to an agent-owned worktree (parent exactly
    `<main checkout>/.agents/worktrees`) — the *resolved* target decides,
    not raw location, but a relative operand needs a base to resolve
    against first:

    ```bash
    git worktree remove --force .agents/worktrees/agentwt                        # cwd = main checkout     -> allowed
    git worktree remove --force .agents/worktrees/agentwt                        # cwd = an agent worktree -> blocked
    git -C <main checkout> worktree remove --force .agents/worktrees/agentwt     # any cwd inside the repo -> allowed
    ```

    A bare relative operand resolves against the session's own `cwd`, so
    the same string is authorized from one `cwd` and blocked from another.
    `-C <dir>` moves that resolution base — a relative operand then
    resolves against `<dir>` instead of the session's actual `cwd` — and
    this now works for `worktree add`/`worktree remove --force` too, the
    same as it already did for `--no-verify`/`commit`/the relaxed-subcommand
    tier. `--git-dir` and `--work-tree` do **not** move this base, since
    neither changes git's working directory: a relative operand alongside
    either of those still resolves against wherever the session actually
    is. An absolute path needs no base at all and always resolves the same.

    **Both an absolute path and `-C <dir>` plus a path relative to `<dir>`
    work from anywhere *inside the repository* — not literally anywhere.**
    `-C` moves the base a relative path resolves against, but it does not
    move the anchor that decides which checkout is "the main checkout" for
    the ownership test itself: that anchor always follows the session's own
    actual working directory, walked back to its own main checkout, never
    the `-C` value. This is deliberate — otherwise a command could aim the
    ownership test at some other repository's `.agents/worktrees` entirely
    — but the consequence is that a shell sitting outside this repository
    can never establish which checkout is "the" main one, so every worktree
    command fails closed there regardless of how the path is written. The
    first two lines above both succeed with the session standing anywhere
    inside this repository (the main checkout or any worktree); none of
    that changes if the session is standing outside it entirely.
- `git tag -d`/`--delete` need no force flag and carry the same
  every-tier denial as `git tag -f`/`--force` in the force-flag family
  above: one tag name is shared by every worktree, and deleting it
  removes that name for all of them at once. Creating and listing tags
  stays allowed, and capital `-F` is a message-file flag, not a force
  flag.
- `git clean` — UNLESS `-n`/`--dry-run` is present
- `git restore <path>` — UNLESS `--staged`/`-S` is present (staged-only
  unstage is safe)
- `git stash drop` / `git stash clear` — and, in every tier, every stash
  take-back that does not name its target's commit hash: `git stash pop`
  in every spelling, plus `git stash apply`/`git stash branch` given a
  stack position (`stash@{n}`, `refs/stash`, bare `stash`) or no stash
  operand. Staying allowed: the add-only forms (`git stash push`/
  `create`/`store`), the read-only ones (`list`/`show`), and take-backs
  that name an explicit commit hash — `git stash apply <hash>`,
  `git stash branch <name> <hash>`. See "The shared stash stack" below
  for where that hash comes from, race-free.
- `git reflog expire` / `git reflog delete` (every other reflog action stays
  allowed) — never relaxes, even inside an agent-owned worktree: the reflog
  is shared with the main checkout.
- `git gc --aggressive` or `git gc --prune=...` (bare `gc`/`gc --auto` stays
  allowed) — never relaxes, for the same shared-state reason.

## The shared stash stack: additive only for agents — capture the hash at save time

The stack is one list shared by every worktree of this repository. The
commands that touch it without destroying anything are the additive ones —
`git stash push`, `git stash create`, `git stash store` — plus the
read-only `git stash list`/`git stash show`. Everything that takes an
entry back off the stack is denied in every tier unless it names that
entry's explicit commit hash: `git stash pop` in every spelling, `git
stash apply`/`git stash branch` given a stack position (`stash@{n}`,
`refs/stash`, bare `stash`) or no stash operand, and `git stash drop`/
`git stash clear` outright. With every positional take-back denied, no
agent-issued command can shrink the stack: it grows until a human prunes
it, and that pruning is a human action performed outside the tool layer —
a known consequence of the identity rule, not a surprise to discover
after the stack has grown.

The hash a permitted take-back names has to come from somewhere, and the
only race-free place to get it is the save itself. `git stash create` is
the one stash command that prints the hash, and it modifies nothing — not
the stack, not the working tree; `git stash store` then puts exactly that
commit onto the stack. Run them as one step and keep the hash where a
later session can find it:

```bash
HASH=$(git stash create "wip: describe the work")    # prints the hash; saves nothing
git stash store -m "wip: describe the work" "$HASH"  # adds that exact commit to the stack
```

`git stash push` saves too, but prints no hash — an agent that saves with
`push` alone has no identity to recover with, and a stash whose hash was
never captured is unrecoverable through the permitted path. Positions are
worthless as names on this stack: another worktree's save between this
agent's save and any later `git stash list` renumbers every entry, so
`stash@{0}` may already be someone else's work — but a hash names an
immutable commit no renumbering can redirect. Recovery by identity, `git
stash apply <hash>` or `git stash branch <name> <hash>`, removes nothing
from the stack (measured), so the entry stays for whoever else needs it.

## The commit gate's set-aside: unstaged edits live in a machine-wide cache while hooks run

Every `git commit` hands the working tree to pre-commit first, and
pre-commit clears unstaged changes for the hooks' duration: it writes
the unstaged diff (`git diff-index --binary`, working tree against the
index) to `~/.cache/pre-commit/patch<ts>-<pid>` (or `$PRE_COMMIT_HOME`
when set), reverts the working tree to the index (`git checkout -- .`),
and re-applies the patch (`git apply`) when the hooks finish. Staged
work survives the whole round trip — the index is both what hooks see
and what the commit carries. A commit killed by a tool timeout
mid-set-aside discards unstaged edits: it never reaches that restore,
and `git status` afterwards reports the file unmodified, while the
only surviving copy of the lost work is the patch file.

No marker exists beyond the cache itself. pre-commit's stash notices
go only to the killed process's own output, `pre-commit.log` is written
only on a caught exception — a SIGTERM/SIGKILL kill is never caught —
and patch files are never deleted, so the cache holds restored and
unrestored entries and the presence of a patch file is not evidence of
a loss. The cache is machine-wide, shared by every repository on this
machine, and its entries carry no repository, branch, or worktree
attribution — an epoch timestamp and a PID — so a recovering agent
cannot reliably identify its own entry: recovery is not merely awkward
but potentially wrong (applying another repository's patch is a real
outcome) and is not prescribed as safe. Before any manual application,
a human must check the entry's timestamps against when the loss
happened and the patch content against the lost file's expected diff.
The convention that avoids the loss entirely: stage everything a
commit is meant to carry before issuing the commit. Loss-mode twin:
`.agents/rules/agent-worktrees.md`'s killed-commit section.

## `--no-verify`: blocked in the main checkout, allowed in linked worktrees

- From the main checkout's working directory, `--no-verify` anywhere in a
  git invocation is still blocked unconditionally, regardless of subcommand.
- From a linked git worktree (e.g. an isolated `.claude/worktrees/agent-*`
  sandbox), `--no-verify` is allowed on the same terms as any other
  currently-unblocked pattern: it does not by itself make an otherwise-safe
  command dangerous. It does not relax any *other* blocked pattern — e.g.
  `git checkout --no-verify` is still blocked because `checkout` is always
  blocked, and `git reset --hard --no-verify` is still blocked because of
  `--hard`.
- Detection is not a hardcoded path check. The hook resolves the *effective*
  checkout location — the session's `cwd`, or the location named by a
  `-C`/`--git-dir`/`--work-tree` override when the invocation carries one,
  the same resolution `git commit`'s check below uses — and walks up from
  there to the nearest `.git` entry: a linked worktree's `.git` is a *file*
  whose `gitdir:` line points at `<repo>/.git/worktrees/<name>`, while the
  main checkout's `.git` is a real directory. If that location is missing,
  unreadable, or not inside any git worktree, the guard fails closed and
  blocks `--no-verify` as before.
- The effective location is a snapshot taken before the command runs, not
  something the guard derives by tracking `cd` inside the command itself —
  see "`cwd` is a snapshot, not tracked shell state" below for the exact
  mechanics and the reliable `-C` form, proven for this check too.

## `git commit` on the main checkout: always blocked

- `git commit` (plain or `--amend`) is blocked unconditionally from the main
  checkout, for every agent-issued invocation, regardless of any run-state
  file. This exists so any agent's work always lands as an uncommitted
  working-tree diff for the human to review and commit themselves — no
  agent commits from the main checkout, ever.
- From a linked git worktree, `git commit` is unaffected by this rule and
  remains fully permitted — per-task commits inside an isolated worktree
  (e.g. a parallel-sdd group's sandbox) are exactly what that mechanism
  relies on and are never blocked by this rule.
- The effective checkout location this rule evaluates is not raw `cwd`
  alone: if the invocation's top-level options include `-C <path>`,
  `--git-dir=<path>`/`--git-dir <path>`, or
  `--work-tree=<path>`/`--work-tree <path>`, that path (resolved against
  `cwd` if relative) is used instead. This closes a bypass where `git -C
  <main-checkout> commit` run with `cwd` set to a worktree would otherwise
  evaluate the linked-worktree check against the worktree and skip this
  block entirely while the commit lands in the main checkout anyway.
- If `cwd` is missing, unreadable, or the effective checkout location can't
  be resolved to a linked worktree at all, the guard fails closed and
  blocks the commit — same fail-closed posture as the `--no-verify` rule
  above.
- This rule cannot detect or "authorize" a human typing `git commit`
  directly in their own terminal — that command never passes through
  Claude's tool layer and is never seen by this hook at all; "only a human
  commits from the main checkout" is the outcome this rule produces, not a
  capability it exercises.
- Not closed by this rule (an accepted, pre-existing limitation of this
  hook's whole design, not new to this rule): a pre-defined shell/git alias
  resolving to `commit` (e.g. `git config alias.ci commit` then `git ci`).
  Every other blocked subcommand in this file (e.g. `git branch -D`) is
  equally alias-bypassable already. The plumbing route out of this rule,
  by contrast, is closed: `commit-tree`, `hash-object`, `mktree`, and
  `update-ref` — the plumbing commands that write objects or move refs
  directly — are denied in every tier (see "Always blocked, regardless of
  flags" above), so landing a commit object and repointing a branch
  without ever invoking the literal `commit` subcommand no longer works.
  The porcelain history-movers (`merge`, `rebase`, `cherry-pick`,
  `revert`, `am`) stay allowed deliberately — the line is drawn at direct
  plumbing writes, not at every command that moves a ref.

## `git push`: blocked except the one canonical branch/PR-workflow form

- `git push` is no longer blocked outright. Exactly one push shape can be
  authorized — `git push -u origin HEAD:<branch>`, the form the parallel
  plan/branch/PR workflow issues from its integration worktree. Every other
  push shape is still denied by shape alone: bare `git push`, `git push origin
  <branch>` (missing `-u`), `--all`, `--mirror`, delete refspecs
  (`origin :<branch>`), non-`HEAD` sources (`origin feature:branch`), and any
  force flag (`--force`/`--force-with-lease`, which lengthens the arg list
  past the exact three-token canonical shape).
- `git send-pack` — the plumbing command underneath `push` — stays blocked
  unconditionally; there is no plumbing-push exception.
- Even for the canonical shape, the push is authorized only when all three of
  the following hold. Any failure denies with a specific reason (never a
  generic "denied"), and every step fails closed when a required fact cannot
  be established:
  1. **Not the default branch.** `HEAD:main` is always denied — the workflow
     never pushes straight to `main`.
  2. **Branch owned by a run that is still running.** The push branch must
     have a per-run state record in the _main_ checkout at
     `docs/runs/plan-runs/<branch>.md` whose `Branch:` field matches
     exactly and whose `Run status:` field is still `InProgress`. The record
     always lives in the main working tree, so a push issued from inside the
     linked integration worktree resolves back to the main checkout (parsing
     the worktree's `.git` `gitdir:` line, the same `.git`-entry walk the
     `--no-verify`/`git commit` rules use) to find it. A missing file, an
     unparsable record, or a mismatched `Branch:` field denies.
  2a. **The run has not been closed.** A record outlives its run: Step 11's
     `Finished` transition leaves the branch and both SHAs standing, so every
     other fact here keeps holding and a closed run's record used to keep
     authorizing pushes indefinitely. `Run status: Finished` now denies with
     its own reason. What may land after a human closes a run is that human's
     decision, and re-opening the run (or starting a new one) is how it is
     made — not a leftover record.
  3. **Commit matches the round's verified SHAs.** The commit `HEAD` actually
     points at — resolved with `git rev-parse HEAD` in the pushing worktree —
     must equal _both_ the record's verify-status SHA and its
     secret-scan-clean SHA. This blocks pushing any commit other than the exact
     one this round ran the project's verify command (configured at
     `[project] verify_cmd` in `.agents/config.toml`) and the secret scan against.
- Detection is not a hardcoded path check. If `cwd` is missing, the main
  checkout can't be resolved, or the pushed commit can't be resolved (git not
  on PATH, `rev-parse` error/timeout/non-zero exit), the guard fails closed and
  denies.
- Same alias bypass caveat as `git commit` above: this is enforced on
  the literal `push` subcommand seen through Claude's tool layer, not on a
  human's own terminal or a pre-defined alias.

## `git config` is fully blocked, both via Bash and via direct file edits

- `git config` is blocked unconditionally via the `Bash` tool, for every
  form — write (`git config core.bare true`) and read (`git config --get
  user.name`, `--list`, `--global ...`) alike. There is no read-only
  carve-out; this is stricter than every other subcommand in this file.
- The file-edit route is enforced by a second, independent `PreToolUse`
  hook, `.agents/hooks/block_git_internals_edit.py` (matcher:
  `Edit|Write|NotebookEdit`). It refuses any file-edit tool call whose
  target lies in one of two protected path classes: **git's administrative
  area** — any path at or below a `.git` entry, including `.git/config`,
  `.git/hooks/*`, `HEAD`, `refs`, and a linked worktree's own `.git`
  pointer file, which is a *file* named `.git` and reachable by no
  filename rule, which is why the guard is a path class — and **the
  plan-run authorization records** the push gate reads (everything at or
  below `docs/runs/plan-runs/`), plus the per-user git configuration
  git reads for every repository on the host (`~/.gitconfig` and the
  `git/` directory under the user's config home — `git config --global` is
  denied on the Bash route, so leaving those writable here would reopen the
  bypass from outside the repository). This closes the bypass where an
  agent edits `.git/config` directly with the `Edit`/`Write` tool instead
  of running `git config` in a shell, which the Bash-only
  `block_git_mutations.py` hook can never see. Logic lives in
  `agentic_workflows/git_internals_edit_guard.py`, tested in
  `tests/unit/test_git_internals_edit_guard.py`.
- **The hooks directory is shared by every worktree, and nothing about the
  directory itself says so.** `.git/config` sets `core.hooksPath` to an
  absolute path into the main checkout's `.git/hooks`, so every linked
  worktree resolves its hooks from that one directory, and one successful
  write into it disables the commit gate for all of them at once — not
  only the worktree the write was issued from. That consequence is
  invisible to a reader of the directory, which is why the rule files
  state it and both surfaces refuse the path class instead of trusting a
  writer to recognize shared state.
- The Bash route to those same two classes is closed for the shapes a
  command names in its own operands, by a companion `PreToolUse` hook,
  `.agents/hooks/block_protected_path_write.py` (matcher: `Bash`):
  redirects (`>` and `>>`), heredocs, `tee`, `sed -i`, `cp`/`mv`/`dd
  of=`/`install` destinations, `ln`, and the delete/permission shapes
  (`rm`, `truncate`, `touch`, `chmod`) are refused when their operand
  lands in a protected class, and a recognized write whose target cannot
  be read (a variable, a command substitution, a glob) is refused
  fail-closed. **What stays open on the Bash route, stated open:** an
  interpreter writing through its own runtime — `python -c`, a script handed
  to an interpreter, a `bash -c`/`eval` body (a redirect inside such a body is one of
  these spellings, not an exception to it), `patch`, `rsync`, `tar` — is
  invisible to an operand recognizer, and that is the same route the
  orchestration's own legitimate record writes travel. Every closure in
  this section names its surface: a refusal on the file-edit route never
  covers the Bash route, and no claim in this file may read as if it did.
  Logic lives in `agentic_workflows/protected_path_write_guard.py` and
  `agentic_workflows/shell_write_targets.py`, tested in
  `tests/unit/test_protected_path_write_guard.py`.
- Neither hook can stop a human editing `.git/config` directly in their own
  editor/terminal, or another local process (a GUI git client, etc.)
  writing to it outside of Claude's tool layer — same class of limitation
  as the alias bypass noted under `git commit` above.

## Left unchanged

- `git remote` keeps its existing allow-list behavior (read-only actions like
  `get-url`/`show`/`-v` allowed, `remote add`/`remove`/`set-url` blocked).

## Everything else is allowed by default

`add`, `commit` (blocked from the main checkout unconditionally — see
"`git commit` on the main checkout: always blocked" above; allowed from a
linked worktree), `branch` (create/rename/safe `-d` delete),
`merge`, `rebase`, `pull` (including `--rebase`), `fetch`,
`stash push`/`create`/`store` and `stash apply`/`stash branch` by hash
(every positional take-back is denied — see the stash section above),
`tag` (create/list allowed — `-f`/`--force` and `-d`/`--delete` are denied
in every tier; capital `-F` stays allowed), `rm`, `mv`,
`cherry-pick`, `revert`, `am`, `submodule` (non-force), `init`, `clone`,
`worktree prune`/`lock`/`unlock`/`move`/`remove` (non-force),
`sparse-checkout`, `notes`, `format-patch`, `fetch-pack`, and read-only
inspection (`status`, `diff`, `log`, `show`, `blame`, `grep`, etc.).

`worktree add` is no longer unconditionally allowed: its `<path>` operand
must itself be agent-owned (a direct child of
`<main checkout>/.agents/worktrees`), or it is blocked — see "Agent-owned
worktrees: a third relaxation tier" above. This is the one entry that moved
out of this "allowed by default" list rather than into it.

- If a command mixes an allowed and a blocked git segment, treat the whole
  command as blocked and remove the blocked step.
- If the user explicitly asks for a blocked git operation, stop and ask for
  confirmation or approval instead of executing it silently.

## Unattended loops and autofix-loop scope

This block is enforced by a real `PreToolUse` hook
(`.agents/hooks/block_git_mutations.py`), not just a norm — it hard-blocks
matching `Bash` calls before they execute. Any unattended iteration loop run
in this repo — a Ralph-Loop-style runner when that plugin is installed (a
live or crashed loop leaves its state file at `.claude/ralph-loop.local.md`;
treat that file as an evidence source about the loop, and skip it when it
does not exist), or a PR-autofix-style loop — will still have `reset --hard`,
`commit` from the main checkout, and the other blocked patterns above
rejected mid-loop, even though `git add`/`git merge` etc. are allowed. `push`
is likewise rejected, with one narrow exception: the canonical
`git push -u origin HEAD:<branch>` form that clears the branch-ownership and
verified-SHA checks (see "`git push`: blocked except the one canonical
branch/PR-workflow form" above); every other push shape stays rejected.
Loops that need to *commit or push* from the main checkout still require a
human (or an explicitly-approved separate step, or running inside a linked
worktree); scope unattended loops that must not commit or push to iteration
that doesn't need those specific blocked operations.

A loop running with `cwd` inside a linked worktree can now also commit with
`--no-verify`, skipping pre-commit checks entirely, without any additional
approval — see the `--no-verify` section above. That is a real expansion of
what an unattended loop can do on its own inside a worktree; it still cannot
push except via the single authorized canonical form, which itself only clears
once the pushed commit matches this round's verify-status and secret-scan-clean
SHAs — so the skipped pre-commit checks must still be caught by that round's
project verify command and secret scan before the branch is merged.

A loop running with `cwd` inside an agent-owned worktree specifically (a
direct child of `<main checkout>/.agents/worktrees`, strictly narrower than
"any linked worktree" above) can go considerably further on its own, with no
additional approval: every subcommand the generated block in "Agent-owned
worktrees: a third relaxation tier" above classifies as worktree-local runs
there regardless of flags, plus force-removing that same worktree
(`git worktree remove --force`), and force-deleting any branch whose name
starts `sdd/` or `plan/` (`git branch -D`). This is an
order-of-magnitude larger expansion than the `--no-verify` one above — an
unattended loop can now discard uncommitted work, rewrite its own working
tree, and destroy its own worktree and branch entirely unsupervised. It
still cannot touch `send-pack`, `config`, `remote` writes,
`gc --aggressive`/`--prune`, or `reflog expire`/`delete` from anywhere,
agent-owned worktree included, and `push` still only clears through the
single authorized canonical form described above — see
`.agents/rules/agent-worktrees.md` for the full rule and its known gaps.
