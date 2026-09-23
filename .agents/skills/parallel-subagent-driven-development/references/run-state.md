State-keeping concern of the parallel-subagent-driven-development workflow, spanning every phase: the run-state record's seven-field header and free-form narrative, and the worktree lifecycle.

## Run-state artifact

The task ledger (`<plan-workspace>/progress.md`, resolved per Step 1 item
4 of `run-start.md`) tracks task-level
progress inside one worktree, and is deleted with that worktree when the
script releases it at the group's merge (Step 6) — so it can never be this
run's own cross-group memory.
This workflow therefore keeps a second, separate record of
cross-group state, one file per run, under `docs/runs/plan-runs/` in
the main working tree (not inside any group's worktree or the integration
worktree), written and updated only by the orchestrating session, via
`agentic_workflows.plan_run_state`'s `write_plan_run_state`/`update_plan_run_state`
— never a raw `write_text_atomic` call constructed by hand.
`record_path_for_branch(branch)` derives the exact path from the run's own
branch name. For each group, record: group ID, worktree path, branch name, dependency
group (if `Sequential`), current state, **which numbered tasks are
complete** (e.g. `Tasks 3/7 complete`), and any autonomous engineering decisions or covered
gaps resolved during the run, in the record's free-form narrative
section below the fixed header.


**The two ledgers now divide one job, and neither is optional.** Per-task
completion lives in `<plan-workspace>/progress.md`
inside each group's own worktree. **The orchestrating session creates that file
itself**, at Step 1, immediately after `.agents/scripts/sdd_workspace.py` resolves the
workspace — that script deliberately writes no ledger — and **is its only
writer** (SKILL.md Step 3 item 3): no subagent ever appends to it. It holds one
line per numbered task, naming that task's number and its outcome, appended
only once that task's work is accepted. That file is
the recovery map a fresh implementer's controller reads after
compaction: a resumed run reads it to learn which tasks already landed, and
dispatches the lowest-numbered task it does not name.
This workflow's own run-state record carries only the rolled-up
count, so a resumed run can tell which group to re-enter without opening every
group's worktree. With one long-lived agent per group these ledgers were
merely advisory; with a fresh agent per task they are load-bearing, because
nothing else remembers which tasks already landed. A group worktree with no
`progress.md` is a defect to fix before dispatching its next task, not a
missing nicety.

**Machine-checkable header block:** the record's **first line** MUST still
be exactly one of `Run status: InProgress` or `Run status: Finished` — the
same single required literal line, checked the same way as before, never a
broader parse. Six more fixed fields follow it, in this exact order,
before any free-form narrative:

```text
Run status: <InProgress|Finished>
Branch: <the run's own branch name>
Integration worktree: <path>
Verify-status SHA: <commit SHA once Step 8 has committed, else empty>
Secret-scan-clean SHA: <commit SHA once Step 9 has passed, else empty>
PR URL: <URL once Step 10 has opened one, else empty>
Terminal outcome: <empty, or a recorded prior failure/success for this run>
```

Initial creation, at Step 0.5 (branch and integration worktree already
created, before the first group worktree is created):

```python
from agentic_workflows.plan_run_state import PlanRunState, record_path_for_branch, write_plan_run_state

write_plan_run_state(
    record_path_for_branch(branch),
    PlanRunState(
        status="InProgress",
        branch=branch,
        integration_worktree=str(integration_worktree_path),
        verify_status_sha="",
        secret_scan_clean_sha="",
        pr_url="",
        terminal_outcome="",
    ),
)
```

At every later field update — Steps 6-11's state and SHA/PR-URL writes, and
Step 11's automatic `Finished` transition — use
`update_plan_run_state(path, **field_updates)`. It read-modify-writes only
the named fields and preserves everything else, atomically (temp file +
rename, reusing this repo's existing `write_text_atomic` helper under the
hood) — the same atomicity guarantee the old raw `write_text_atomic` calls
gave, so a reader always observes either the fully-old or fully-new
content, never a partial file.

**Compaction checkpoints are keyed to notification-turn ends, never wave
boundaries.** A notification turn is a turn triggered by dispatched work
reporting back — the turn boundary a continuous-dispatch run can actually
rely on; in ZCode, the notification-turn lifecycle in `zcode-compat.md`
owns it. At every such turn's end, and at the pre-integration checkpoint
immediately before Step 7, this record and every unfinished group's ledger
are already current on disk — the turn's own processing wrote them (ledger
appends, registry entries and clears, field updates) — so auto-compaction
at any later point loses no state, and the next dispatch decision starts
from a fresh disk re-read (SKILL.md Step 3), never from remembered context.
The retired wave-boundary key named an event continuous dispatch no longer
creates: with no batch barrier there is no wave boundary to checkpoint on.

States a group moves through: `Grouped` → `WorktreeReady` → `InProgress` →
(`Blocked` and back) → `AwaitingMerge` → (`ConflictHalted(Landing)` and
back) → `Merged`. A group enters `ConflictHalted(Landing)` when its landing
merge conflicts or its post-merge scoped checks fail and the orchestrator's
2 bounded resolution attempts did not clear it — its worktree is retained,
holding its slot, until the human resolves the escalation. Once every group
reaches `Merged`, the whole run moves to
`FinalReviewPending`, then through Steps 7-10 (`VerifyPassed` →
`SecretScanClean` → `Pushed` → `PROpened`/`PRUpdated`), then `Finished`
once the run's pull request is open and the automatic cleanup has released
the integration worktree (Step 11) — no human confirmation gates that
transition; the PR review is the run's human checkpoint.

## In-flight registry

Dispatch and harvest must never lose each other across compaction or
session death, so every dispatched-but-not-yet-harvested task is recorded
in a disk-first **in-flight registry**. **Write-before-dispatch: the entry
is written before the dispatch is issued** (dispatch-and-briefs.md binds
the dispatch side of this rule). **Clear-on-harvest: the entry is cleared
when the task's completion is harvested, and only after the ledger line
naming it is appended.** A task the registry or a ledger names as in flight
or complete is never dispatched again **while its registry entry stands**.

- **Storage shape is implementation discretion** — a body section of this
  record below the pinned seven-field header, or a convention in the group
  ledgers. No helper script enforces it: the notification-turn checklist
  (`zcode-compat.md`) is the enforcement. The header itself never carries
  it — its seven fields and their order are pinned, and the registry is
  derived state, not a run fact.
- **Entry identity is the ledger's task key** — one entry per dispatched
  task, named exactly as the group's ledger names it, so the harvest-time
  dedup check (an existing ledger line naming the task means the completion
  is processed no further) and the entry share one key.
- **The orchestrating session is the registry's only writer**, as it is of
  every ledger (dispatch-and-briefs.md binds the brief side).
- **Stranded entries clear only through reconciliation.** An entry whose
  task has no pending dispatch is stranded — reconcile it at the next
  dispatch decision, not later: stop any still-running orphan first (by
  whatever stop mechanism the harness provides), then clear the entry only
  when the task is verifiably complete (a ledger line names it) or
  verifiably never dispatched (no ledger line and no worktree change
  attributable to it — a fresh implementer may then be dispatched,
  mirroring the fresh-dispatch-on-Blocked doctrine). No third clearing
  path exists.
- **The registry is derived, rebuildable state, never a source of truth** —
  the ledgers and the worktrees are the truth it summarizes. After a killed
  session or a mid-run harness switch it may be rebuilt from the ledgers
  and each worktree's git log, and discarded entirely; nothing outlives the
  run.

## Worktree lifecycle

Worktrees are **acquired** (created or reused) only through
`.agents/scripts/worktree_acquire.py acquire`, which enforces the per-run cap N
from `.agents/config.toml` (`--run <branch>` names the calling run) and
leases each worktree to exactly one run; other runs' worktrees — leased or
not — never count against a run and are never touched by it. Worktrees are
**released** only through the same script's `release` subcommand, which
enforces the durability invariant (below). Raw `git worktree add`/
`git worktree remove` commands are prohibited to agents —
`.agents/rules/agent-worktrees.md` owns that prohibition, backed by a
Claude Code hook (in harnesses without hooks it is prose-only, an accepted
loss recorded in `zcode-compat.md`).

**The orchestrator never renews a lease — there is no renewal and no
timer.** A live holder is never auto-reclaimed; freeing a slot is the
owning run's explicit, durability-gated release. A resumed run reclaims
its own stale holders deterministically: `status --run <branch>` to list
them, `release --name <name> --run <branch>` for each, then `acquire`
again.

The lifecycle is automatic and rolling:

- **A group's worktree is released immediately after its branch merges into
  the integration branch and the post-merge scoped checks pass** (Step 6) —
  that frees its on-disk slot for the next waiting group.
  The group's branch is kept; only the worktree goes, so a post-verify
  attribution fix or the human can re-create a worktree from the branch.
- **The integration worktree is released once the run's pull request is
  opened** (Step 11) — exactly one per run, exempt from the cap while the
  run's state record names it `InProgress`.
- **A `ConflictHalted(Landing)` group's worktree is the one retention** —
  it holds its slot until the human resolves the escalation.

**The durability invariant governs both removal and destructive
reuse.** Before a worktree is removed OR re-synced to another branch tip,
any uncommitted work MUST be committed to the holder's branch (or the tree
verified clean). The same
mechanical precondition makes the automation safe: what the old cleanup
confirmation step protected is protected by commit-before-land
instead, which is checkable, not judgment. **Freeing a slot
happens only through the owning run's explicit `release`**: when the
calling run's own tree is dirty, release commits the uncommitted work to
its branch before removing the tree (commit-then-remove, never a discard);
a dirty tree held by another run is refused — your run never touches
another run's worktree.

Every worktree in this lifecycle lives at `.agents/worktrees/<name>` — the
one agent-owned root — and its lifecycle states (free / held / released)
are the script's lease ledger's business, recorded
under that root; the run-state record carries only each group's worktree
path and workflow state, never the ledger's.

