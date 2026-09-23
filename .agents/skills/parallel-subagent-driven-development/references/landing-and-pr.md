Landing and delivery phase of the parallel-subagent-driven-development workflow: rolling dependency-order merge landing with scoped checks per merge, the single integration review, the handoff verification, the verified-SHA record, secret scan, push, pull request, automatic durability-gated cleanup, and the close-out that reconciles the run's own planning documents (Steps 6 through 12).

## Step 6: Land each group by rolling dependency-order merge — never patches, never a queue

### Single-Group Fast Path (1 Group = Direct No-Op Landing)
When the plan decomposes into **exactly one task group**, Step 0.5 and Step 1 unified the group's worktree with the run's integration worktree. All tasks were executed directly in that worktree on the run's branch — which IS the integration branch.
- **Skip the merge:** there is no separate group branch to merge — the group's accepted work is already on the integration branch as the implementers' commits.
- Confirm the work is committed: `git status --porcelain` reports a clean tracked tree and the group's tasks appear in `git log`.
- Proceed directly to Step 7.

### Multi-Group Rolling Landing (2+ Groups)

Groups land **as each completes** — no landing queue, no batch, no tie-break
ordering: the moment a group's last task passes `sdd-reviewer` acceptance and
its work is committed to its own branch, that branch merges into the
integration branch. Dependency order constrains the merge *sequence*, not the
*timing*: a `Sequential (must follow <group>)` group's branch merges only
after every group its label names has reached `Merged`; independent groups
merge in completion order. A plan with more groups than N slots relies on
exactly this rolling behavior — each merge frees the merged group's on-disk
slot for a waiting group (item 3 below). Land one merge at a time — never two
merges concurrently, even if two groups completed in the same turn.

**Precondition per group (durability).** Every task's implementer
committed its work to `sdd/<group-slug>` inside the group's worktree as its
tasks were accepted (the dispatch brief instructs this), and
`git status --porcelain` in that worktree reports a clean tracked tree before
the merge. Landing an uncommitted branch is refused: commit the work to the
group's branch (in the group's worktree) first — never merge a dirty tree.

For each group as it completes:

1. Merge its branch from the integration worktree:
   `git -C <integration-worktree-absolute-path> merge --no-ff sdd/<group-slug> -m "merge <group-slug>: <summary>"`
   — with the integration worktree as the command's effective checkout
   location, per the mechanical requirements above. `--no-ff` is required:
   it writes one merge commit per group, and the per-merge commit history is
   how a failed handoff verify is attributed (Step 7) — a fast-forward would
   erase exactly that attribution.
2. Run the group's **scoped checks** — only what its merged files demand
   (never the project's verify command; exactly one full verification per
   run exists, at
   Step 7's handoff):
   - Touched Python files under the project's source or test trees: run the
     project's configured lint, typecheck, and test commands on exactly the
     touched paths — **per merge**, because each of these genuinely narrows
     to the paths given and costs roughly what those paths cost.
   - If the project has a JavaScript/TypeScript package (package.json at
     repo root or in a UI subdirectory): run that package's lint, typecheck,
     and test scripts over the touched files (scoped by the runner's own
     filtering to touched spec files where practical) — **once per landing
     wave, not once per merge.** Run them after the last merge of the
     current landing sequence, the point at which no other group is ready to
     merge this turn, over the union of every package path those merges
     touched. A whole-project typecheck cannot narrow below the entire
     package at all, so running it per merge pays the identical
     whole-project cost once for every group instead of once for the wave.
   - **The accepted cost, stated:** a frontend regression is attributed to a
     landing wave rather than to one group's merge. `--no-ff` keeps one merge
     commit per group either way, so the attribution is recoverable by
     bisecting that wave's merges — what is traded is the immediacy of the
     signal, never the ability to find its source. A wave of one merge is
     unchanged in every respect.
3. On pass, release the group's worktree **immediately and automatically**:
   `python3 .agents/scripts/worktree_acquire.py release --name <group-slug> --run <run-branch>`
   (the run's own branch from Step 0.5 — only the owning run can release).
   This is not a human checkpoint — the durability precondition is
   the committed branch above, a mechanical fact, not a judgment call. If
   the tree somehow carries uncommitted work, release commits it to the
   branch before removing — never a discard); a refusal here means
   a real defect (or a skipped precondition) — fix that, never bypass by
   hand. The group's
   **branch is kept** — only the worktree goes, so a post-verify attribution
   fix (Step 7) or the human can re-create a worktree from it. Record the
   group as `Merged` in the run-state record; its slot is now free for a
   waiting group.

**Conflict path.** If the merge hits a conflict, or the
post-merge scoped checks fail:

- The landing sequence for that group halts. Its worktree is **retained**,
  still holding its on-disk slot; nothing of the group is deleted or
  reverted.
- The merged-and-checked prefix — every earlier group's merge — is kept
  as-is, and the run's other groups are unaffected: sibling groups keep
  landing. There is no cross-group halt.
- The orchestrator attempts **bounded resolution: at most 2 attempts**,
  working either in the retained group worktree (sync it to the integration
  branch tip, resolve, commit to the group branch, re-merge per item 1) or
  in the exempt integration worktree (resolve the conflict in place and
  commit). A failed scoped check is resolved the same way — fix, commit,
  re-merge, re-run the scoped checks.
- If resolution fails after 2 attempts, the group enters
  `ConflictHalted(Landing)` in the run-state record and escalates to the
  human, naming the conflicting files or the failing checks. The retained
  worktree holds its slot until the human resolves it.

## Step 6.5: The findings phase — every admitted finding, fixed once

Every finding the admission gate admitted (`run-start.md` Step 0.1), and that
the run did not already fold into the task that was editing those same files,
is fixed **here, in one pass, and nowhere else**. This step is the only place
this workflow issues a dedicated fix dispatch.

**Why a phase rather than a running repair.** Measured across the two runs in
flight on 2026-09-21: one run's thirteen tasks recorded 48 findings, its group
acceptance review returned 18 more, and the three fix tasks created to take
those 18 recorded 22 findings of their own — the last batch's eight all closed
with no change made. Fixing each finding where it appears makes the run's own
output its own input, and nothing in that shape decides when to stop.
Collecting them and taking them once does.

**One pass, stated as a rule that does not negotiate.** Issue every admitted
finding's fix in one wave, then stop. A finding a fixer in this wave
discovers is **recorded and reported, never fixed**: it goes in the final
message beside the gate's refusals, marked `raised inside the findings phase`.
There is no second wave, no re-review of this wave's own diff, and no
exception for a finding that looks small or cheap — the bound is the whole
mechanism.

What runs here, in order:

1. Read the run-state record's findings register and list every admitted
   finding still open.
2. **Collapse the duplicates before anything else, because deferring created
   them.** While findings were repaired where they appeared, a fix removed its
   own cause and no later reviewer met it again; now every finding sits open
   for the whole run, so two groups touching one file report one defect twice.
   Measured 2026-09-21 across the two runs then in flight: of 244 findings,
   106 named a file another finding also named (`src/config.py` alone was
   named by eight, `agentic_workflows/plan_references.py` by eight); of the other
   run's 73, 40 did (`agentic_workflows/style_contract.py` by nine). Those counts are
   the population to inspect, not a duplicate count — two findings about one
   file are often two real defects.
   **Merge two entries only when one fix closes both**, and carry every merged
   entry's id and citation into the surviving entry, so the final message
   still reports each finding that was made. When one fix would not close
   both, leave them apart: a merge that hides a second defect costs more than
   a dispatch that repeats a first.
3. **Re-test what survives against the landed tree before fixing it.** A
   finding raised against one group's worktree can already be gone once every
   group has merged, and a dispatch aimed at a finding that no longer exists
   is pure cost. A finding that no longer reproduces is closed in the register
   with what was re-run. Re-testing follows the collapse so a merged defect is
   re-tested once rather than once per entry.
4. Group what survives by the files it touches and issue one fix dispatch per
   file-disjoint set, **all in the same turn**, so the phase costs one wave of
   wall-clock rather than one per finding. This grouping is what puts every
   remaining finding about one file in front of a single fixer; it is not a
   second deduplication and never substitutes for step 2.
5. Record every dispatch's outcome in the register, then close the step.

**An empty register closes this step immediately**, and that is the expected
shape of a run whose admission gate did its job — not a failure, and never a
reason to go looking for work.

**Nothing re-reviews what this phase fixed.** Its diff is part of the
consolidated diff that Step 7 reads, which is where this run's only code
review happens.

## Step 7: One final code-review-fix-loop run over the consolidated diff

**Pre-Review Context Compaction**: Run `/compact` immediately before dispatching `code-review-fix-loop` to clear out accumulated task cards, tool calls, and landing traces from the orchestrator context before review begins.

Once every group has landed (Step 6), dispatch `code-review-fix-loop` exactly
once, with `cwd` set to the integration worktree, **unmodified end-to-end,
including its own Step 8**. Do not give it a `--scope` flag — the loop's
baseline BASE (the integration branch's pre-run state, recorded in the
run-state record's narrative at Step 0.5) makes `git diff BASE` exactly this
run's full consolidated diff: every group's merge from Step 6, and nothing
that predates the run.

This dispatch's own Step 8 verify call (the project's verify command,
configured at `[project] verify_cmd` in `.agents/config.toml`) **is** the
single integration
gate for the whole mechanism, and the only full verification of the run —
the per-merge scoped checks of Step 6 are the only verification that ran
earlier. The orchestrating session MUST NOT make any separate, earlier
verify call, and no per-group dispatch has made one either.

**This Step 7 dispatch is the only `code-review-fix-loop` run of the entire
workflow, and this file is the single owner of when it runs.** Not once per
task, not once per group, not once per worktree, not once per wave, and not a
second time after a fix. Every earlier step is forbidden from dispatching it
for any reason, however small the change or however tempting an early pass
looks. A group's own per-group pass is an acceptance gate against the plan's
stated criteria, not a code review, and it never substitutes for or duplicates
this one — see `dispatch-and-briefs.md`'s Step 2.

If this run's verification fails:

1. Attribute via the per-merge commit history: walk the run's per-group merge
   commits from Step 6 (`git log --merges BASE..HEAD` in the integration
   worktree; `git show --name-only <merge-sha>` for each group's file set) —
   bisect down to the single group whose merge introduced the failure. There
   are no patches and no worktree-local diffs to compare anymore; the merge
   commits are the attribution record.
2. Single-group attributable:
   - Re-create a worktree for that group from its retained branch via the
     acquire script (`acquire --name <group-slug> --branch sdd/<group-slug> --run <run-branch>` —
     slots are free because Step 6 released the group's worktree at its
     merge).
   - Fix there, commit to the group branch, and land per Step 6's exact
     mechanism (rolling merge, scoped checks, automatic release).
   - Re-run the verify command **directly** — a plain invocation of the
     project's verify command,
     not a fresh `code-review-fix-loop` dispatch. The review dimensions
     already passed clean before verification failed, so re-running them
     is redundant.
3. Cross-group, or touches a file no live group owns: escalate to the human
   with the failing test and the candidate groups' file sets — do not guess,
   do not auto-patch.

Once this run reports a clean pass and its verify call passes,
proceed immediately to Step 8 — do not stop here, and do not report the
integration branch as unfinished output. Everything is already committed at
this point (Step 6's merges and the loop's own batch merges); Step 8 records
that fact.

## Step 8: Record the verified SHA

This run's work is already fully committed on the integration branch — the
groups' merges (Step 6) and the loop's own batch merges carry every change;
there is no landing-round commit left to make. Confirm nothing uncommitted
appeared: `git -C <integration-worktree-absolute-path> status --porcelain`
must report no tracked modifications. Uncommitted tracked state at this
point means the durability gate was bypassed somewhere upstream (an
implementer or fixer reported without committing) — halt and fix that
defect rather than committing over it. Then write the integration branch's
HEAD SHA into the run's state record's `Verify-status SHA` field via
`update_plan_run_state` (from `agentic_workflows.plan_run_state`) — the same SHA the
push authorization (Step 10) requires.

## Step 9: Secret scan

Before pushing anything, scan for secrets in two places using
`agentic_workflows.secret_scan`:

1. `scan_diff_for_secrets` against the run's full diff —
   `git diff <BASE>..HEAD` in the integration worktree, where BASE is the
   pre-run state recorded at Step 0.5 and HEAD is the SHA Step 8 recorded.
2. `scan_text_for_secrets` against the PR description text drafted for
   Step 10.

On any match: hard-stop. Name the location of the match (file and line) in
the report to the human — never the matched value itself. Do not proceed to
Step 10.

On a clean pass: write that same commit's SHA into the run's state record's
`Secret-scan-clean SHA` field via `update_plan_run_state`.

## Step 10: Push and open/update the PR

Push using exactly this canonical form — no other push form is ever used by
this workflow:

```bash
git push -u origin HEAD:<branch>
```

- **First push for this run:** call `find_open_pull_request`, then
  `create_pull_request` (both from `agentic_workflows.github_client`) to open
  a PR against the base branch (default `main`) for the pushed branch. Write
  the returned PR URL into the run's state record's `PR URL` field.
- **Continuation push (a PR already exists for this run):** first call
  `get_pull_request_state`. Require it to return exactly `"OPEN"` before
  pushing — for any other value (`MERGED`, `CLOSED`, or an unrecognized
  value), halt and name the actual returned state in the message rather than
  pushing. Once confirmed `OPEN`, push, then call
  `update_pull_request_description` with the round's updated content.
  Both `get_pull_request_state` and `update_pull_request_description` take
  the PR number (`pr_id`), not its URL — derive it from the trailing
  `/pull/<number>` of the `PR URL` stored in the state record (a GitHub PR
  URL always ends in `/pull/<number>`).

The full GitHub PR API contract — `gh` authentication (`gh auth login`) and
the three-value PR-state enum — is documented once, centrally, at
`.agents/rules/github-pr-api.md`. Do not restate it here; reference it.

## Step 11: Automatic cleanup — the PR review is the human checkpoint

Cleanup waits for no human approval: the
lifecycle is automatic, gated only on the mechanical durability precondition, and the
human checkpoint for the run is the pull-request review itself, not a
cleanup confirmation.

1. **Group worktrees were already released** — each one immediately after
   its merge passed the scoped checks (Step 6 item 3). A group sitting at
   `ConflictHalted(Landing)` is the one exception: its worktree is retained,
   holding its slot, until the human resolves the escalation.
2. **Release the integration worktree** once the run's PR is open (Step 10):
   `python3 .agents/scripts/worktree_acquire.py release --name <run-slug> --run <run-branch>` —
   automatic, no human approval — exactly one integration
   worktree per run, deleted once its PR is opened. The durability check is
   mechanical and already satisfied — Step 8 confirmed the tree clean — so
   a refusal means tracked state appeared after Step 8: fix that defect,
   never bypass by hand. The run's **branches are retained**: the run branch
   is the PR's head, and the group branches stay for post-verify attribution
   fixes and re-created worktrees.
3. **Flip the run-state record to `Finished`** via `update_plan_run_state`.
   This transition is now automatic — it follows the PR opening and the
   release above, never a human confirmation.

Nothing was ever pushed before its own verify passed (Steps 8-10), so there
is no "discard before committing" path here. Merging, closing, or approving
the PR stays exclusively the human's own action on GitHub — this
workflow never attempts any of those.

**Recovery, not a gate:** if a stale state record is ever found stuck at
`Run status: InProgress` with no live orchestrating session behind it (e.g.
a killed/lost prior session), a human may instruct the orchestrator to
abandon the run at any time — flip the record and release or discard the
run's retained worktrees (the Step 0 discard path covers force-removal where
the human has ruled uncommitted work expendable).

**Final response to the user:**
When the run ran in an autonomous mode — question-option 1 from Step 0.1, or
any of `--dont-stop`/`--dont-ask` — the final message delivered to the human
upon completing Step 11 MUST render the **Plain-Language Autonomous Decisions Table**
(Step 0.1), presenting all autonomous choices, architectural decisions, and resolved
gaps in a clean, easily readable Markdown table.

When `--dont-defer` was active, the same final message MUST additionally render
the **Findings & Fixes Table** from the run-state record's findings register:
every finding surfaced during the run (by implementers, reviewers, fixers, or
the integration review), the fix applied to it, and where it landed — in the
same easy, plain language, so the user can audit what was taken and why
without reading the diff.

The same message MUST also name every finding the admission gate
(`run-start.md` Step 0.1) refused, and which of its three classes refused it.
A refusal is a judgment the user is entitled to overturn, and one that reaches
nobody is indistinguishable from a finding nobody made — which is the silence
`.agents/rules/findings-go-in-decision-notes.md` exists to prevent. Keep it to
one line each: what was seen, and why it was not taken.

## Step 12: The close-out — reconcile the planning documents the run refused to touch

`run-start.md` Step 0.1 refuses every finding about the run's own planning
documents while the run executes, and its refusal text says reconciling those
documents "belongs to the close-out". This step is that close-out — defined
here rather than left ambient, so the refusal has a destination and no run
parks its paperwork on a step nobody performs.

- **Owner:** the orchestrating session. It alone holds the findings register
  naming every reconciliation item the run parked, so it is the only role
  that knows the complete list.
- **Trigger:** the run's own finish — the state record is `Finished` and the
  PR is open (Step 11). Until then the documents are still moving and nothing
  may be reconciled; after it, the orchestrating session asks the owner about
  the parked items once, and applies exactly the edits the owner approves.
- **Scope:** the reconciliation items the class-3 refusals carried — a stale
  citation, a premise a landed task proved false, a sentence the run's own
  work left missing. Each approved edit is made once; an item the owner does
  not approve stays reported in the final message and is never silently
  dropped.

The close-out reconciles documents and nothing else: no code change, no
second findings wave, no re-review of the PR. A defect found here that is not
about the run's own planning documents goes back through the admission gate
(`run-start.md` Step 0.1) like any other finding.

