ZCode compatibility layer for the parallel-subagent-driven-development
workflow: the substitutions a ZCode orchestrating session applies, the losses
it accepts, and the procedure for switching an in-flight run onto this layer.
Claude Code sessions never apply anything here — SKILL.md routes them past
this file — and nothing in it redefines any step: it maps harness mechanisms
only, and every step's semantics stay owned by SKILL.md and its other
references.

## When this annex applies

The orchestrating session is in ZCode when its `Agent` tool offers only
untyped agent types (`general-purpose`, `Explore`, judge variants) — so it
cannot dispatch the native `sdd-implementer`/`sdd-reviewer` specialists
defined in `.agents/specialists/`, cannot pass a per-dispatch `model`, has no
`/compact` command, and executes none of `.claude/settings.json`'s
PreToolUse hooks. Detect it from the `Agent` tool's own type list at dispatch
time, never from a remembered claim about the session — the substitutions
below attach to the tool's actual capabilities, not to a session label.

## Substitutions

1. **Typed specialist dispatch → role-file-briefed `general-purpose`.**
   Every implementer dispatch is a `general-purpose` Agent call whose brief's
   first instruction reads `.agents/specialists/sdd-implementer.md`; every group
   acceptance review reads `.agents/specialists/sdd-reviewer.md`; each subagent
   treats that file's Critical Invariants, handback contract, and workflow as
   its binding role. This overrides dispatch-and-briefs.md's "never dispatch
   untyped `general-purpose` subagents" rule in ZCode — that rule's stated
   rationale (inherited MCP schemas, unpinned model, bloated system context)
   is exactly the accepted loss recorded below. The role files remain the
   single authoring location: never copy their prose into a brief, into this
   annex, or anywhere else.
2. **Model-tier pins (`model:` frontmatter, the standard-capability floor,
   `effort: max`) → session model, recorded.**
   ZCode's Agent tool takes no model argument; every dispatched role runs on
   the session's model. Proceed and name the deviation in the run-state
   narrative — `.agents/rules/model-assignment.md` is unsatisfiable here, an
   accepted loss (below), never a halt.
3. **`tools:` frontmatter scoping → restated one-path authorization.**
   ZCode gives every subagent every tool, so the reviewer's near-read-only
   allowlist is unenforceable. The dispatch brief restates the reviewer's
   write authorization verbatim from its role file: the group notes path, and
   nothing else.
4. **Ambient `.claude/rules` auto-load → in-brief instructions only.**
   Nothing auto-loads in ZCode beyond root `AGENTS.md`.
   dispatch-and-briefs.md's unconditional in-brief instructions (the
   python-antipatterns + clean-typing read, the grounding-artifact path, the
   per-task scratch root, the unfiltered-read budget, the autonomy
   instruction) are load-bearing in ZCode, not redundancy: every brief states
   each one, every time.
5. **PreToolUse hooks → the script's own enforcement, plus guard-approved
   shapes.** `block_git_mutations.py`, `block_large_file_dump.py`, and the
   grep blocker do not run in ZCode, so no command is blocked mechanically.
   The worktree lifecycle enforces itself everywhere, hooks or not: run the
   whole thing through `.agents/scripts/worktree_acquire.py`
   (`acquire`/`status`/`release`) — its cap refusal, lease exclusivity, and
   durability refusal are script logic, not hook logic. What ZCode
   additionally loses is the raw-`git worktree add` *backstop*: nothing
   mechanically blocks a hand-rolled worktree command here, so the
   prohibition is prose-only (accepted loss, below). For git commands the
   workflow issues directly, use exactly the shapes SKILL.md's mechanical
   requirements prescribe (`git -C <worktree-absolute-path> <subcommand>`;
   the canonical push form), because a violation that Claude Code's guard
   would block here simply executes. The 120-line unfiltered-read
   budget and the `rg`-only search rule are brief-level prose in ZCode.
6. **`/compact` checkpoints → disk-first state, re-read on every notification
   turn.** No `/compact` command exists; ZCode compacts automatically. At
   every notification turn's end, and at the pre-Step-7 checkpoint, write
   the run-state record and ledgers current to disk. Re-read the run-state
   record (via `parse_plan_run_state`) and each unfinished group's
   `<plan-workspace>/progress.md` before dispatching anything — after any
   context summarization, and on every notification turn (lifecycle step 1
   below).
7. **Step 4 status bar placement → invoke `progress-report`, final message
   of the turn.** ZCode reliably renders only the final message of a turn;
   text between tool calls may not display. Invoke the `progress-report`
   skill — the Skill tool loads its exact spec on demand, which is what
   keeps the bar correct after context summarization — and emit the bar it
   specifies as the last block of the turn's closing message, never between
   tool calls.
8. **Parallel dispatch mechanics → background dispatch with notification
   turns.** Dispatch every implementer as an `Agent` call with
   `run_in_background: true`; the harness notifies you when each finishes,
   and that completion notification — not a batch boundary — ends your turn
   and re-invokes you. That is Step 3's greedy continuous dispatch made
   executable: one implementer finishing frees its slot while unrelated
   in-flight agents keep running; never wait for all of them. Multiple
   foreground `Agent` calls issued in one message still run concurrently —
   the loop's parallel fix-batch mechanism — but they are not the dispatch
   mechanism. The cap is unchanged in kind: at most N in-flight
   implementers, at most one per group, N from `.agents/config.toml` via
   `agentic_workflows.worktree_capacity.load_max_concurrent_worktrees` — the
   acquire script enforces the worktree half of that cap in ZCode exactly
   as it does in Claude Code. The cap counts two slot kinds, and they free
   at different events — do not conflate them: **An agent slot frees at
   task completion** (a group's next-task dispatch needs only a free agent
   slot and the group's held worktree). **A worktree slot frees only at
   merge landing** plus the acquire script's release (new-group dispatch
   stays merge-gated by `.agents/scripts/worktree_acquire.py` exactly as today).
   Run the notification-turn lifecycle below on every wake event.

## The notification-turn lifecycle

Never create a turn solely to report or poll: interval `TaskOutput` polling
is prohibited, and no timer, no poll, and no harness event other than a
completion notification re-invokes you — a completion notification is the
only automatic wake event. (A human reply to a surfaced stall or HITL
question is the recovery path that rule leaves open, not a wake event to
schedule work around.) `TaskOutput(block=false)` is allowed
for exactly two purposes: a recovery probe when a notification is suspected
lost (the turn-end check below), and harvesting a completed task's result
when the notification itself does not carry one. A notification turn is a
work turn: state re-read, ledger update, refill, bar.

Never redispatch a task while its registry entry stands. The in-flight
registry is disk state — a run-state body section or a ledger convention —
recording every dispatched-but-not-yet-harvested task, keyed by the ledger's
task key. Its invariants are write-before-dispatch (write the entry, then
issue the dispatch) and clear-on-harvest (clear the entry when the
completion is harvested). The only other way an entry clears is step 3's
reconciliation rule.

Run this checklist in order, every notification turn, skipping no step:

1. **Re-read disk state** before any dispatch decision: the run-state
   record (via `parse_plan_run_state`) and each unfinished group's
   `<plan-workspace>/progress.md`.
2. **Harvest every completion this notification delivers** — one
   notification may carry several. For each: fetch the result (the
   notification payload, or a `TaskOutput(block=false)` harvest when it
   does not carry one); process the handback card; then apply
   dedup-before-append — check the group ledger for an existing line naming
   the task before appending, and a completion already recorded is
   processed no further; otherwise append the ledger line and clear the
   task's registry entry.
3. **Reconcile the registry**: any remaining entry whose task has no
   pending background task is stranded — apply the reconciliation rule now,
   not later. `TaskStop` a still-running orphan first, then clear the entry
   only when the task is verifiably complete (the ledger names it) or
   verifiably never dispatched (no ledger line and no worktree change
   attributable to it — a fresh implementer may then be dispatched).
4. **Refill**: evaluate every group for dispatch. Work counts as
   dispatchable eligible work only when it passes every condition: the
   Sequential gate satisfied (via `dependency_wait_satisfied`); not named
   by the in-flight registry or a completed ledger line; an agent slot
   free; and, for a new group, a worktree slot free.
5. **Register before dispatch** (register-before-dispatch): write the
   registry entry for each eligible task, then issue its
   `run_in_background: true` Agent call — all eligible work goes out in
   this turn, without waiting for unrelated in-flight agents.
6. **Report conditionally**: emit the progress bar only if this turn
   changed task, group, or run state, as the last block of the turn's final
   message (substitution 7).
7. **Turn-end check**: Never end a turn holding dispatchable eligible work
   while zero background tasks are pending, unless the run is finished or
   halted for the human — "halted for the human" is run-level only: a group
   awaiting human escalation or a deliberate run pause; a group-level
   `ConflictHalted(Landing)` is not a run halt, and its sibling groups keep
   dispatching. Zero pending background tasks with a non-empty registry is
   a defect signal, not a legal resting state: run the recovery probe now —
   `TaskOutput(block=false)` over the registry; a confirmed-complete-but-
   unharvested task runs step 2's harvest in this same turn. Zero pending,
   nothing harvestable, and dispatchable eligible work remaining means no
   wake event exists — surface the stall to the human in this turn's final
   message (which group, which task, what state) instead of silently
   waiting.

**Degradation note — background dispatch unavailable → same-turn batch dispatch.**
When the `Agent` tool offers no `run_in_background`, fall back
to Step 3's same-turn dispatch: issue each wave's Agent calls together in
one message in batches of ≤ N, starting the next batch only after at least
one agent from the current batch completes, and run checklist steps 1-2 at
each batch boundary. This note exists so a future client without background
support degrades without a spec change.

## What does not change

Grouping labels and Sequential waits, one fresh implementer per numbered
task, the per-group acceptance gate, orchestrator-only ledger writes, the
worktree mechanics of Steps 0.5-1 (including the single-group fast path) —
script-
mediated acquisition, cap enforcement, and the rollout `status` gate all
run in ZCode as they do in Claude Code — landing by rolling dependency-order
merge, Step 7's single integration `code-review-fix-loop`, the project's
verify command
exactly once at handoff, the verified-SHA record, secret scan, push/PR, and
the automatic durability-gated cleanup — all run
exactly as SKILL.md and its references define them.

## Accepted losses (documented, not recoverable by prose)

- **Named-agent dispatch** (substitution 1): there are no native typed
  specialists in ZCode — `sdd-implementer`, `sdd-reviewer`, and every
  registered review dimension run as role-file-briefed `general-purpose`
  agents. The registry dispatch never happens, so the definition's own
  metadata (tool scoping, handback-contract injection, model pin) never
  auto-applies; the brief must carry everything the definition would have.
- **Definition-level model pins** (substitution 2): every agent
  definition's `model:` pin (the `model:` frontmatter pins, including the
  deeper-model-pinned reviewers)
  is unenforceable in ZCode's Agent tool — each dispatch runs on the
  session's model. This extends the per-dispatch model-routing loss below
  to the pins themselves: spend per run may exceed
  `model-assignment.md`'s assumption — the relevant incident history is
  design-notes.md §The 2026-08-08 quota-exhaustion incident.
- **Parallel fix batches** (substitution 8): the loop's parallel fixer
  waves run concurrently in ZCode as same-turn Agent calls — the mechanism
  the lifecycle's degradation note falls back to when background dispatch
  is unavailable — but every fixer is a `general-purpose`
  agent under the named-agent loss above — no `sdd-implementer`
  definition, no model pin — so per-batch spend is bounded only by the
  cap N, never by model routing.
- **Per-dispatch model routing** (substitution 2): every implementer and
  reviewer runs on the session's model, so spend per run may exceed
  `model-assignment.md`'s assumption.
- **Harness tool scoping** (substitution 3): a reviewer's write discipline is
  prose-only.
- **Mechanical guards** (substitution 5): git-mutation shapes, read budgets,
  search-tool rules, the raw-`git worktree add` prohibition's hook backstop,
  and the review loop's iteration cap
  (`limit_review_loop_iterations.py`) are unenforced until a runner script
  owns them — the acquire script's own cap/durability refusals are the
  worktree-lifecycle enforcement that does work here, because it is script
  logic rather than hook logic.

## Step 7: running code-review-fix-loop in ZCode

`code-review-fix-loop` is a standalone skill under `.agents/skills/`, and
ZCode's skill loader drops any skill whose frontmatter description exceeds
1024 characters — at 1687 it was silently absent from ZCode's registry
(Claude Code has no such limit, which is why the same file loaded fine
there). The description is now under the limit; if the skill ever
disappears from ZCode's registry again, measure the description first —
that is the known cause, and a unit test pins the description's portability. Its substitutions:

- **Dimension 1 (`code-reviewer`) and Step 7 (`code-simplifier`) named
  dispatches → role-file-briefed `general-purpose`**, same pattern as
  substitution 1: the brief's first instruction reads
  `.agents/specialists/code-reviewer.md` (or
  `.agents/specialists/code-simplifier.md`), and — because
  the named-subagent route existed precisely so repository rules would be
  auto-injected — it also reads root `AGENTS.md` and the `.agents/rules/`
  files the role file cites. Nothing auto-injects in ZCode; the brief
  carries what the registry would have.
- **Dimensions 2-9 (`Explore` dispatches) run natively**: ZCode has an
  `Explore` agent type, and each dimension's brief ("Load and follow
  \<specialist file\>. Report findings only — do not edit any file.") is
  already the load-a-file form this pattern uses.
- **The iteration cap loses its mechanical enforcement**:
  `.agents/hooks/limit_review_loop_iterations.py` is a PreToolUse hook and
  does not run in ZCode, so the 5-iteration cap is prose-only here — count
  the loop's iterations out loud in each report, and treat the
  confirming-full-pass rule as the orchestrator's own discipline.
- Everything else — the diff snapshot, the deterministic scanners, the
  in-coordinator SYNTHESIZE pass, sequential working-tree fixes, narrow
  VERIFY, and the single final run of the project's verify command — is shell
  and file work that
  runs exactly as the skill defines it.

## Handback-card authority

The card a dispatched role returns is whatever its role file defines — six
lines today, carrying a `Not covered` field — and the orchestrator records it
verbatim; a brief never restates or narrows the card. If dispatch-and-briefs.md
and a role file ever drift apart again, the role file wins: it is the text the
subagent actually runs under, and realigning the reference to it is the fix,
not a note.

## Switching an in-flight run onto this layer

Nothing on disk needs re-creating: branches, worktrees, ledgers, and the
run-state record are harness-agnostic. To switch a run already being
orchestrated by an improvising ZCode session:

1. Stop dispatching new work in that session for one turn.
2. Reconcile state before the next dispatch: if the run has no record under
   `docs/runs/plan-runs/`, create it (`write_plan_run_state`) from what
   already exists; if any group worktree lacks
   `<plan-workspace>/progress.md`, backfill one line per already-accepted
   task from the worktree's own git log and notes — a missing ledger is a
   defect to fix before that group's next dispatch, per run-state.md.
3. From the next dispatch turn on, apply every substitution above: read this
   file in that session, dispatch remaining tasks as role-file-briefed
   `general-purpose` agents, and put the Step 4 bar in the turn's final
   message.
4. Never restart the run, re-create worktrees, or redo landed groups to
   "convert" them — a landed group is already correct output regardless of
   which harness dispatched its work.

A subagent already in flight when the switch lands finishes its task under
its old brief; the substitutions bind from the next dispatch.
