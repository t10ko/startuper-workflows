---
name: parallel-subagent-driven-development
description: Use for every executable plan detailed-plan.md produces — COMPACT, STANDARD, or ARCHITECTURE, one task group or several — the moment that plan is approved and its Execution Queue begins. Never for an INVESTIGATION plan (produces no production edits) or a WORKFLOW_DOCS plan (docs/prompt text only, no executable-behavior change), and never picked proactively by a user request on its own. An agent never commits from the main checkout — only from a worktree.
---

# Parallel Subagent-Driven Development Workflow

**The session whose plan `.agents/workflows/detailed-plan.md` just approved MUST
invoke this workflow itself, immediately, before implementing anything.**
This is not a choice weighed per plan — it is the one and only execution path for every
`COMPACT`, `STANDARD`, or `ARCHITECTURE` plan, the moment its Execution Queue
begins. It is never picked proactively by a user request on its own, and it
is never skipped because a plan happens to decompose into one task group
instead of several: one group still runs through this same workflow's Steps
0-11. Under the single-group fast path, when a plan decomposes into
exactly one task group, the run's integration worktree (Step 0.5) also
serves directly as the group's worktree (Step 1), eliminating a second
worktree acquisition, duplicate toolchain syncs, and a separate landing
merge (Step 6 is a fast no-op),
while the single integration-level `code-review-fix-loop` pass (Step 7),
verification, and PR creation (Steps 8-10) run as normal.
Grouping (`Independent (parallel-safe)` vs `Sequential (must follow
<group>)`, from `detailed-plan.md`'s Execution Queue) only ever decides how
many worktrees run at once — Step 1 — never whether this workflow runs at
all.

This workflow owns its inner loop outright — one implementer subagent per
numbered task, a reviewer over the group's work, and a fix pass over what that
review finds, one task in flight at a time inside one checkout, stated in full
at `references/dispatch-and-briefs.md`. What it adds around that loop is one
checkout per group (one, or several running concurrently, depending on
grouping) so the loop always runs off the main checkout, never on it, and the
rolling dependency-order merge landing that folds each group's committed
branch into the integration branch inside a dedicated integration worktree as
the group completes, the one integration `code-review-fix-loop` pass and its
handoff verification (the project's verify command), then the secret scan,
push and pull-request sequence that ends with the run pushed and opened as a
GitHub pull request (see Steps 6-10). Worktree cleanup is automatic throughout — a group's worktree is
released the moment its merge lands and its checks pass, and the integration
worktree is released once the run's pull request is open; the PR review is
the run's human checkpoint, not a cleanup confirmation.

The design history behind Steps 0.5 and 8-10 lives in this skill's
`design-notes.md`, not restated here; the single-group fast path's history
is at `design-notes.md` §The single-group cost gap.

Even once that gap is closed, this workflow still applies the same branch,
worktree, review, verify, and pull-request sequence to a one-line
`COMPACT` fix as to an `ARCHITECTURE` plan — a deliberate choice, not an
oversight. The two confirmed failures that made this workflow's invocation
unconditional in the first place were both proportionality-shaped. A
size-based exemption from this workflow re-opens exactly that judgment
call. Until a narrower, still-unconditional way to scale the cost is
designed and proven not to reopen it, every executable plan pays this cost
in full. Failure history: design-notes.md §The two proportionality-shaped
failures.

Never assume this orchestrating session already has
`.agents/rules/block-git-mutations.md` in context — `.claude/rules`
deliberately excludes it from ambient auto-load. Its narrower companion,
`.agents/rules/agent-worktrees.md` (the agent-owned-worktree rule this
workflow's own worktree acquisition and automatic cleanup rely on), **is**
auto-loaded — but the full deny-list, including the `--no-verify`/
`git commit` linked-worktree carve-outs the inner loop's implementer
commits (Step 2) and the push (Step 10) depend on, is not.
Read `block-git-mutations.md` before Step 0.5: this workflow issues
`git merge`/`git push` directly from this session (Steps 6, 10) and other
git-mutating commands throughout (Steps 0.5, 6). The live
`.agents/hooks/block_git_mutations.py` hook enforces the same deny-list
regardless of whether this session has read the file, but reading it first
avoids losing a turn to a blocked command shape discovered only by
attempting it.

**Two mechanical requirements this workflow's git operations must follow:**

1. **Every worktree this workflow creates, inspects, or removes goes through
   `.agents/scripts/worktree_acquire.py` (`acquire`/`status`/`release`) — never a
   raw `git worktree add` or `git worktree remove` command.** The script
   enforces the per-run cap N from `.agents/config.toml` (`acquire` and
   `release` take `--run <branch>` naming the calling run), leases each
   worktree to exactly one run, and refuses to remove or re-sync a worktree
   whose uncommitted work is not committed to its branch (the durability
   invariant) — a raw command bypasses all of that, and is prohibited to
   agents by `.agents/rules/agent-worktrees.md` (backed by a Claude Code
   hook; in harnesses without hooks the prohibition is prose-only, recorded
   as an accepted loss in `references/zcode-compat.md`). The script's own
   contract — stdout, exit codes 0/1/2, and what each refusal means — is
   owned by `.agents/scripts/worktree_acquire.py`'s module docstring; never restate
   it here. Never use a tool that writes to `.claude/worktrees/` instead —
   that location is outside the agent-owned root.
2. **Every `git commit`/`git merge`/`git push` this workflow issues must run
   with its target worktree as the command's effective checkout location,
   via `-C` rather than relying on the orchestrating session's own `cwd`
   already being there.** The recommended, cwd-independent form is
   `git -C <worktree-absolute-path> <subcommand>` (e.g.
   `git -C <integration-worktree-absolute-path> merge --no-ff <group-branch>`
   at Step 6) — this is proven to resolve `-C` correctly for `commit`,
   `merge`, and `--no-verify` alike, so it works regardless of the
   orchestrating session's own `cwd` at that moment. Relying on the
   session's own `cwd` already being the target worktree, without `-C`, is
   fragile: this workflow's orchestrating session is not guaranteed to
   still be sitting in that directory by the time the command runs.

**Harness routing (ZCode).** If this session's `Agent` tool exposes only
untyped agent types — `general-purpose`, `Explore`, judge variants — instead
of the native `sdd-implementer`/`sdd-reviewer` specialists, it is running in
ZCode: read `references/zcode-compat.md` before Step 0 and apply its
substitutions at every step it names, for the whole run. Claude Code sessions
that dispatch the native specialists are untouched by that reference — for
them every step runs exactly as this document and its other references
define it.

## Input

A set of tasks from an approved, executable plan (`COMPACT`, `STANDARD`, or
`ARCHITECTURE`), each already assigned to a group. Two labels exist, applied
by `.agents/scripts/parallel_plan_grouping.py`'s `label_groups()` or, when that
function was not actually run, by hand against the exact rule it implements
— file-path overlap across each task's declared exact file paths is the
primary signal, `Consumes`/`Produces` interface-contract overlap is the
secondary signal; either collision downgrades the affected group(s) to
`Sequential`:

- `Independent (parallel-safe)` — this group's declared files, and its
  `Consumes`/`Produces` contracts, do not collide with any other group's.
- `Sequential (must follow <group>)` — this group must not start until
  `<group>` has fully landed (reached state `Merged`).

**Execution-mode flags.** The invocation may also carry three flags —
`--dont-stop`, `--dont-ask`, `--dont-defer` — that fix the run's execution
mode before anything is created: continuous non-stop execution,
best-judgment decisions with no conversational questions, and the
Zero-Deferral Gate that fixes every finding its admission gate admits and
reports all of them in the final message. Any flag present skips Step 0.1's autonomy
question entirely, so a run started from `detailed-plan.md`'s recommended
command never re-asks how to execute; an axis no flag names runs this
workflow's standard default. `run-start.md` Step 0.1 is the single owner of
what each flag changes and of the hard invariants no flag ever overrides.

Read the whole labeled task list before creating anything. A plan with only
one group still enters this workflow — see Step 0.5 and Step 1 below. There
is no separate path, and no single-group shortcut, that
skips branch and worktree creation for that case.

When the plan cites a grounding artifact, the orchestrating session settles
its freshness before reading it or naming it in any brief.

**Grounding freshness** — before reading any grounding artifact body, follow `.agents/references/grounding-freshness.md`, the single owner of the staleness-check protocol and of what each exit code obliges you to do.

`label_groups()` itself raises `ValueError` (naming the groups involved)
instead of emitting labels when it detects a circular `Sequential`
dependency — e.g. group A's `Consumes` matches group B's `Produces` and
group B's `Consumes` matches group A's `Produces`. That check runs upstream,
before this workflow is ever invoked, precisely so no group can ever be
labeled `Sequential (must follow <group>)` in a cycle: this workflow's
dispatcher (Step 3) never has to detect a live cycle itself, because
`dependency_wait_satisfied()` would otherwise poll forever with neither
group in the cycle able to reach `Merged` first. If labeling raised that
error, this workflow is never reached at all — escalate to the human to fix
the plan's task grouping before retrying.

- **Run start (Steps 0, 0.1, 0.5, 1)** — interrupted-run check, the
  execution-mode flags (`--dont-stop`/`--dont-ask`/`--dont-defer`) and the
  autonomy gate, branch and integration-worktree creation, and per-group
  worktree fan-out — lives at
  `.agents/skills/parallel-subagent-driven-development/references/run-start.md` — read it when starting a run, before creating any branch or worktree.

- **Dispatch and briefs (Step 2)** — the inner implementer/reviewer loop, subagent role selection, the ban on passing a model argument, the 6-line handback contract, the per-group single review pass, and the verification, unfiltered-read and scratch-root budgets every brief must state — lives at `.agents/skills/parallel-subagent-driven-development/references/dispatch-and-briefs.md` — read it when writing any dispatch brief or choosing a subagent role.

## Step 3: Dispatch across groups concurrently, respecting Sequential waits

The orchestrating session — not a nested agent — is the one that dispatches
work across groups. Every dispatch turn first re-reads disk state before any
dispatch decision — the run-state record (via `parse_plan_run_state`) and
each unfinished group's `<plan-workspace>/progress.md` — never remembered
context. Then, every dispatch turn:

1. For each group not yet `Merged`: if it is `Independent`, it is eligible
   for worktree creation (Step 1) and task dispatch immediately. If it is
   `Sequential (must follow <group>[, <group>...])`, it is eligible for
   **both** worktree creation and task dispatch only when
   `dependency_wait_satisfied(dependency_group_states)` (from
   `.agents/scripts/parallel_plan_grouping.py`) returns `True` — that is, **every**
   group its label names shows every task complete in its ledger **and** a
   run-state entry reading exactly `Merged`. A `Sequential` label carries a
   comma-separated list, because a group can genuinely gate on more than one
   other group; read it with `parse_sequential_label()` and pass one state per
   named group, never a single state. Waiting on only one of several
   dependencies dispatches the group off a tip the others' work has not landed
   on. The label alone is not the gate; this check is. Any dependency sitting
   at `AwaitingMerge` or `ConflictHalted(Landing)` still blocks the wait — treat those the same as "not yet
   merged," and leave the waiting group at `Grouped`, polling this check
   again next turn.
2. Dispatch every eligible group's next-ready task in the **same turn** —
   everything eligible goes out now and nothing eligible waits for unrelated
   in-flight work; one dispatch per ready **task**, at most one task in
   flight per group.
   - **Greedy Continuous Dispatch**: Dispatch eligible groups continuously up to the worktree/concurrency cap N read once per run from `.agents/config.toml` (`[worktrees] max_concurrent`, via `agentic_workflows.worktree_capacity.load_max_concurrent_worktrees` — never hardcode the number; N is human-only, agents never change it). The moment an upstream group merges, an in-flight task finishes, or a `Blocked` group resolves and a slot of the matching kind frees up, immediately evaluate waiting groups and dispatch newly eligible groups/tasks without waiting for unrelated running groups to complete. The two slot kinds free at different events — **an agent slot at task completion, a worktree slot only at merge landing** (Concurrency cap, below) — so a group's next-task dispatch never waits behind a merge, and a new group's first dispatch never starts before its worktree slot frees.
   - A group that finishes a task while a sibling group is still mid-task does not wait for it; only the landing step (Step 6) is ever serialized. Within a group the next task's implementer is a **fresh** subagent, dispatched only once the previous task's review is clean or its findings are parked with rulings — never the same agent resumed onto new work, which is exactly how one context grows past 700k.
   - **Cadence here, mechanism there.** This step owns the cadence — what is
     eligible and when it must go out — and never the wake-and-dispatch
     mechanism, which is harness-provided: a ZCode orchestrating session
     dispatches and refills through `references/zcode-compat.md`'s
     background-dispatch substitution and runs its notification-turn
     lifecycle on every wake event (its degradation note covers a harness
     without background dispatch). Every dispatched task is registered
     before its dispatch is issued — dispatch-and-briefs.md's
     register-before-dispatch rule.
3. The orchestrating session is the only writer to any group's ledger. An
   implementer subagent must never append to its own group's
   `<plan-workspace>/progress.md` — if one does, that is a defect in how the
   subagent was briefed, not a state the ledger should record.
4. If an implementer inside a group reports `BLOCKED`, that group stops at
   that task: do not dispatch its next task, do not record that task complete
   in its ledger, and move the group to `Blocked` in the run-state record with
   the reported reason. Resolve the blocker in this session when it is this
   session's to resolve — an ambiguous requirement, a ruling the plan never
   made, a dependency that has not landed — and escalate to the human only
   when it is not. Clearing it means dispatching a **fresh** implementer onto
   that same task with the resolution written into its brief, never resuming
   the blocked agent. Sibling groups keep running unaffected. The blocked
   group's landing is simply withheld until it clears `Blocked` back to
   `InProgress`.
5. **Orchestrator Compaction Protocol (`/compact` Checkpoints)**:
   - **Checkpoint keys — owned by `references/run-state.md`:** the
     checkpoints are **notification-turn ends** — the turns on which
     dispatched work reports back — never wave boundaries; continuous
     dispatch creates no batch boundary to key on. At each such turn's end
     the run-state record and every unfinished group's ledger are current on
     disk. In Claude Code, issue `/compact` at those same turns when context
     depth is expanding; ZCode compacts automatically and maps this protocol
     through zcode-compat substitution 6.
   - **Pre-Integration Checkpoint:** ALWAYS run `/compact` immediately prior to dispatching Step 7 (`code-review-fix-loop` on the integration worktree) to clear accumulated subagent status cards and tool traces.
   - **Context Ceiling — owned by the harness setting, never restated here.** The single owner of how deep an orchestrator context may grow is `CLAUDE_CODE_AUTO_COMPACT_WINDOW` in `.claude/settings.json`; this workflow states no threshold of its own, and a number written back into this file is a second writable store of that value (`.agents/rules/single-source-of-truth.md`). Compact at the checkpoints above — which are events, not sizes — and let the configured window catch whatever they miss.

- **Step 3.5 was removed** — per-group `code-review-fix-loop` passes are eliminated; the reasoning and what replaced them is recorded in this skill's `design-notes.md`.

- **Status reporting (Step 4)** — invoke the `progress-report` skill for every status report, **once per orchestrator turn that changes task, group, or run state** (never a turn created solely to report) and on every state transition: it is the single owner of both the required progress-bar layout and the cadence at which a bar may be drawn, along with its concurrency lanes and the exact fill arithmetic every bar must satisfy — read it when emitting a status report, before drawing any bar, and never restate its layout or its cadence here.

- **Step 5 was removed** — the actual-diff-overlap pre-flight belonged to the
  old patch-apply landing, which no longer exists. Under rolling branch
  merges, a file-set overlap between groups surfaces as a native merge
  conflict at Step 6 and follows that step's conflict path; the note is in
  this skill's `design-notes.md`.

- **The findings phase (Step 6.5)** — every admitted finding the run did not
  fold into the task already editing those files is fixed there, in one wave,
  after all groups land and before Step 7. It is the only place this workflow
  issues a fix dispatch, and a finding raised inside it is reported rather than
  fixed. Lives in `landing-and-pr.md`.

- **Landing and PR (Steps 6-12)** — rolling dependency-order merge landing
  with scoped checks per merge and automatic worktree release, the one
  integration `code-review-fix-loop` and its handoff verification, the
  verified-SHA record, the secret scan, the single authorized push form and
  PR call, and the automatic durability-gated cleanup — lives at
  `.agents/skills/parallel-subagent-driven-development/references/landing-and-pr.md` — read it when a group is ready to land, and again before any commit, push or release.

- **Run state and worktree lifecycle** — the run-state record's exact seven-field header, how it is written and updated, the per-group state machine, and the automatic worktree lifecycle (when a worktree is removed, and what the durability invariant demands first) — lives at `.agents/skills/parallel-subagent-driven-development/references/run-state.md` — read it when recording or reading run state, and before releasing any worktree.

## Scope this workflow does not cover

- Consumer-project data directories that are gitignored (so a fresh
  worktree never has a copy of them) — this mechanism only applies to
  git-tracked changes (source, tests, `.agents/`, `docs/`, config).
- Any task marked `live_api` (gated by `--allow-live-api`). Real outbound
  network calls and their rate limits/cost make concurrent execution across
  groups a serialization case, not a parallelism target for this mechanism —
  such a task runs on its own, outside the concurrent-group model.
- The project's fixed-port development services (local databases, sidecars,
  and similar). Only the verify command configured at `[project] verify_cmd`
  in `.agents/config.toml` and the scoped checks are established as
  collision-free across concurrent worktrees; this workflow never runs the
  project's dev servers per group.
- **Concurrency cap: per run, N worktrees, N agents in flight — N from
  `.agents/config.toml`** — this workflow's instance of
  `.agents/AGENTS.md`'s repo-wide cap. N's single machine-readable owner is
  `.agents/config.toml` (`[worktrees] max_concurrent`), read through
  `agentic_workflows/worktree_capacity` by `.agents/scripts/worktree_acquire.py` and the
  Claude Code hook backstop; agents never change it. The cap counts
  **worktrees leased to the calling run under `.agents.worktrees/`** (other
  runs' worktrees never count against a run and are never touched by it;
  the run's single integration worktree is exempt, so groups and
  review-fix batches hold all
  N slots), and it equally bounds **in-flight implementer subagents** —
  the two coincide only because Step 3 holds at most one implementer in
  flight per group, so each in-flight agent holds exactly one worktree.
  Making the task the dispatch unit therefore does not widen this cap — a
  group with twelve tasks still contributes exactly one running agent, it
  just contributes twelve short ones in sequence instead of one enormous
  one. The two slot kinds free at different events, and Step 3's refill
  honors each kind's own event — do not conflate them: **An agent slot
  frees at task completion** — a group's next-task dispatch needs only a
  free agent slot and the group's held worktree, and never waits for a
  merge. **A worktree slot frees only at merge landing** plus the acquire
  script's release — new-group dispatch stays merge-gated by
  `.agents/scripts/worktree_acquire.py` exactly as today. When more groups are
  eligible than the cap allows, they queue in batches of ≤ N — a queue
  size, not a wait trigger: a queued batch starts as soon as a worktree
  slot frees (a merge landing plus Step 6's automatic release), never only
  after the whole running set drains, and a queued group never delays a
  started group's next-task dispatch, which waits only on the agent slot a
  task completion frees. This cap prevents API quota
  exhaustion under large plans
  (quota-exhaustion incident history: design-notes.md §The 2026-08-08
  quota-exhaustion incident). The script's own refusal when the cap is
  full is the primary backstop; the only other is reactive: Step 1's
  halt-on-failure check.
