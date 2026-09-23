---
name: code-review-fix-loop
description: RUNS EXACTLY ONCE PER BODY OF WORK, AT THE VERY END, OVER THE WHOLE COMBINED DIFF — never per task, never per task group, never per worktree, or partway, never a second time. Iterates REVIEW→SYNTHESIZE→FIX→VERIFY until zero real findings or the iteration cap, then runs the project's verify command once. Dispatches code-reviewer, silent-failure-hunter, security-reviewer, pr-test-analyzer, type-design-analyzer, comment-analyzer, py-antipattern-specialist, duplication-reviewer in parallel; code-simplifier once after a clean pass. Synthesizes one judged list before any fixer; partitions findings into at most N file-disjoint batches; fixes each batch with a parallel sdd-implementer in an integration-tip worktree; lands batches by rolling dependency-order merge with scoped checks. Never pushes; the human reviews and pushes. Use when the user says "review and fix this PR", "run the review loop", "autofix the review findings", "clean up this diff until review is happy", or invokes /code-review-fix-loop.
disable-model-invocation: false
argument-hint: "[--max-iterations N] [--scope <path>]"
---

# code-review-fix-loop

Iterate REVIEW → SYNTHESIZE → FIX → VERIFY against the current scoped diff until a full pass turns up nothing real to fix, or `--max-iterations` (default 5) is hit — then run the project's verify command configured at `[project] verify_cmd` in `.agents/config.toml` once, report, and stop. REVIEW and SYNTHESIZE read the diff in place; FIX dispatches `sdd-implementer` fixers into worktrees acquired from the cap-managed pool and lands each batch's branch by rolling merge. The loop's only git writes are the baseline commit it requires before FIX and the batch-branch merges it lands; it never pushes, and it never runs `code-simplifier` mid-loop (see Step 7).

Parse `--max-iterations N` (default 5) and `--scope <path>` (default: whole repo) out of `$ARGUMENTS` before Step 1.

## Run this once, at the very end, over everything combined — never in pieces

**This skill runs exactly once per body of work, after all of that work is
finished and combined into one diff.** Never once per task, never once per task
group, never once per worktree, never once per wave, and never as a "quick pass"
partway through. It is the last thing that happens before a human looks at the
change, and there is only ever one of it.

Running it in pieces is the expensive failure it exists to avoid: every extra
run re-reads the whole diff from scratch, multiplying the cost by the number of
pieces while finding the same cross-cutting problems over and over. A finding
that spans two pieces cannot be seen at all until they are combined, so the
split runs cost more and see less.

When this skill runs inside the parallel-subagent-driven-development workflow,
that workflow's Step 7 is the single place it is dispatched from, and that
workflow is the owner of when — see
`.agents/skills/parallel-subagent-driven-development/references/landing-and-pr.md`.

## When to use

- All the work is done and combined, and the complete change needs one review-and-fix pass before a human sees it.
- The user invokes `/code-review-fix-loop` directly on a finished body of work.

## When NOT to use

- Any part of the work is still unfinished, still in another worktree, or still unlanded — wait until everything is combined, then run once.
- A single task, group, or file just finished and it is tempting to review "just that" — that is the split this skill forbids.
- The scoped diff is empty — say so and stop; there is nothing to review.
- The user wants a single one-shot review with no autofix — dispatch the `code-reviewer` agent directly instead.
- The user wants the change implemented, not just cleaned up — this skill only fixes findings against work already done; it does not design or implement new behavior.
- The user wants the eventual push to happen automatically — out of scope everywhere in this repo (`.agents/rules/block-git-mutations.md`), not just for this skill. The loop lands fixes as merges on the integration branch; the human reviews the result and pushes.

## Steps

### 1. Scope the diff

```bash
git rev-parse HEAD                  # run ONCE per run, before anything lands — this commit is BASE
git status --porcelain              # lists untracked (`??`) new files, which a diff never shows
```

- The scoped diff is `git diff BASE` (plus the `??` entries from `git status --porcelain`). BASE is the state this run's work began from: inside the parallel-subagent-driven-development workflow it is the integration branch's pre-run state (that workflow's run-start records it); standalone it is HEAD as of this step's first invocation of the run.
- If the scoped diff is uncommitted working-tree state and fixes are wanted, commit that work to the run's branch before the first fix dispatch — one baseline commit; it is the material under review, not something the loop authored — and keep BASE at the commit before it. The fix phase's worktrees sync to the integration branch tip and cannot see uncommitted changes. The loop's own git writes stay limited to the batch-branch merges it lands.
- Every iteration's scoped diff is `git diff BASE` — never `git diff HEAD`. The loop's own batch merges move HEAD, and diffing against moving HEAD would silently shrink the surface under review as batches land.
- If `--scope <path>` was given, scope the commands to that path (`git diff BASE -- <path>`, `git status --porcelain -- <path>`).
- `??` entries inside scope are new files — read them directly (treat the whole file as "added" for review purposes) rather than assuming the diff covers everything in scope.
- If both come back empty inside scope, stop and report that there is nothing to review. Do not manufacture findings.
- Re-run this step at the top of every loop iteration (Step 6). **Iteration 1 sweeps the whole scoped diff; iteration 2 and later narrow to the union of files the previous iteration's fixers edited — each fixer's status card carries a `Files Changed:` line, and the union of those lines is the list — plus the files cited by findings deferred into this iteration (Step 3e) — *except* the iteration that follows a narrowed pass finding zero real defects, which re-widens to the whole scoped diff, because Step 6 requires one full confirming pass before the loop may exit clean.** Narrowing gives up something real: while an iteration is narrowed, nothing mechanical catches a fix's fallout in a file no fixer touched — Step 5's scoped checks catch lint, type, and test breakage, not a review dimension's own judgment (a duplicated block, a convention mismatch, a silent-failure pattern in a file outside the narrowed union). Step 6's confirming full pass, not VERIFY, is what closes that gap, and only right before the loop is allowed to exit.
- This narrowing shipped without the A/B guardrail its own decision record called for — the decision adopting yield-based narrowing named "A/B a gated run against a full run on the same diff" as the guardrail before adopting it, and that comparison has not been run. Step 6's required final full pass is the mitigation substituted in its place, not proof the guardrail was satisfied.

Write this step's output to one snapshot file the reviewers read, instead of having each of them re-derive the same diff. Fill in `<path>` with `--scope <path>`'s value on iteration 1, the narrowed file list on iteration 2+, or drop every `-- <path>` below when unscoped:

```bash
mkdir -p verify/review_reports
SNAPSHOT=verify/review_reports/code-review-fix-loop-diff.md
# Track intent-to-add for untracked files so the diff naturally includes them as standard unified diffs
git add -N -- <path> 2>/dev/null || git add -N .
{
  echo '## git diff BASE'; git diff BASE -- <path>
  echo '## git status --porcelain'; git status --porcelain -- <path>
} > "$SNAPSHOT"
```

- Rewrite the snapshot at the top of every iteration; it is this iteration's static input for every dimension. (`verify/` is gitignored, so it never leaks into the handoff diff — the same convention dimensions 7 and 9 already use for their scanner reports.)
- Before dispatching anything in Step 2, confirm `$SNAPSHOT` exists and is non-empty. A missing or empty snapshot is not evidence of a clean diff — it means the write failed (permissions, disk, a lock on `verify/`) or this step ran out of order. Fix that and re-run this step; do not dispatch reviewers against it. This is the same discipline dimension 9's `## SKIPPED` gate already applies elsewhere in this file: an unreadable snapshot must never be silently treated as zero findings.

### 2. REVIEW — dispatch every applicable specialist in parallel

Ten review dimensions exist. Up to nine are dispatched per loop iteration (one always-on, eight conditional); the tenth (`code-simplifier`) only runs once, after Step 6 exits clean (see Step 7). Determine which of the nine apply to the *current* scoped diff before dispatching anything — skip a dimension outright if its condition doesn't hold; don't dispatch it just to have it report "not applicable". On a narrowed iteration (Step 1, iteration 2+), "the current scoped diff" is that narrowed slice, not the whole diff — a dimension whose condition fails against the narrowed slice can still be true of the whole change. Record every skip with which scope it was evaluated against (e.g. "skipped: this iteration's narrowed files don't touch `.py`", not a bare "skipped: diff doesn't touch `.py`"), so the Report never reads as "inapplicable to this change" when it only means "inapplicable to this iteration's slice".

**On iteration 2 and later, also skip a dimension that produced zero confirmed real defects in the previous iteration — but only after the three gates below, evaluated in order.** First, the marker exemption: dimension 1 (`code-reviewer`) is the iteration marker, and it is exempt from the yield skip — it dispatches on every iteration no matter what it yielded before, because the enforced iteration cap counts the marker's dispatches and a yield-skipped marker would make that count stop matching the passes the loop actually ran (its table condition is "Always" anyway). Second, the condition skip: a dimension whose condition fails on this iteration's scope is skipped there and recorded against that scope before any yield is consulted. Third, the dispatched precondition: the yield-skip test requires that the dimension was dispatched in the previous iteration — a dimension that did not run carries no yield evidence, whether it was condition-skipped against that iteration's scope or was a dimension 7/9 scanner that short-circuited without dispatching its classifier — so it dispatches whenever its condition holds, and its prior skip stays a condition skip, never a yield skip. Only a dimension past all three gates reaches the yield test, which is Step 3b's "real defect" bucket, not the raw count a reviewer reported: a dimension whose every finding was dropped as already-handled or overfit yielded nothing and is skipped the same as one that reported nothing at all. Iteration 1 is unaffected — it dispatches every applicable dimension, always. Record a skip decided this way as a **yield skip**, named separately from a condition skip in the Report, because the two mean different things: a condition skip says the dimension cannot apply, a yield skip says it applied and found nothing worth fixing.

**Step 6's confirming full pass re-dispatches every applicable dimension, with no yield skips at all.** This is the same re-widening the file narrowing already obeys, and for the same reason: the pass that lets the loop exit clean must be a pass over everything, by every dimension, or "clean" was never established. A dimension re-dispatched there that turns up a real defect restarts the loop normally, and from the next iteration the yield skip applies again.

**The accepted loss, stated:** while an iteration is yield-narrowed, a dimension silent in the previous round cannot catch a defect a fix has just introduced in its own area. This is the same shape of gap as the file narrowing above, and it is closed the same way and at the same moment — by Step 6's required full pass, not by VERIFY. It also inherits that narrowing's unmet guardrail: the decision adopting yield-based narrowing asked for an A/B of a gated run against a full run on the same diff before adoption, and that comparison has still not been run for either narrowing.

| # | Dimension | Dispatch | Fires when |
|---|---|---|---|
| 1 | General code quality / AGENTS.md conformance | Registered subagent, dispatched by name: `code-reviewer` — the iteration marker the dispatch cap counts per loop pass | Always |
| 2 | Silent failures / error handling | Registered subagent, dispatched by name: `silent-failure-hunter`. Report findings only — do not edit any file. | Diff (in scope) touches executable source (`.py`, `.ts`, `.tsx`, `.sh`, `.sql`) |
| 3 | Security (OWASP Top 10, secrets, injection, `shell=True`) | Registered subagent, dispatched by name: `security-reviewer`. Report findings only — do not edit any file. | Diff (in scope) touches executable source (`.py`, `.ts`, `.tsx`, `.sh`, `.sql`) |
| 4 | Test coverage | Registered subagent, dispatched by name: `pr-test-analyzer`. Report findings only — do not edit any file. | Diff (in scope) touches a test file: `tests/**`, `test_*.py`, `*_test.py`, or a `.test.ts`/`.test.tsx`/`.spec.ts` file in the project's JavaScript/TypeScript package (if it has one) |
| 5 | Type design / invariants | Registered subagent, dispatched by name: `type-design-analyzer`. Report findings only — do not edit any file. | Diff introduces a new type: new `class ...(BaseModel)` / `class ...(TypedDict)` / `@dataclass` / `Protocol` / `NewType(` in Python, or new `interface ...` / `type X = ...` in TypeScript |
| 6 | Comment / docstring accuracy | Registered subagent, dispatched by name: `comment-analyzer`. Report findings only — do not edit any file. | Diff adds or changes a comment or docstring: `#` lines, `"""..."""` blocks, `//`, `/** */` |
| 7 | Typing-contract antipatterns (`Any`, `cast(`, `object`, `Mapping[`, `getattr(`/`hasattr(`, `model_dump(`) | Scanner run directly by the coordinator (below), **plus** one registered subagent, dispatched by name: `py-antipattern-specialist`, pointed at the scan output at `<path>` to classify every candidate `FIX_IN_BATCH`/`LEGIT_BOUNDARY`/`FALSE_POSITIVE`/`NEEDS_REVIEW`. Classify only — do not edit any file; fixers apply fixes later. | Diff (in scope) touches any Python source file (and scanner finds >=1 candidates) |
| 8 | DRY / duplication | Scanner run directly by the coordinator (below), **plus** one registered subagent, dispatched by name: `duplication-reviewer`, pointed at the scan output at `<path>` to classify every candidate `FIX_IN_BATCH`/`LEGIT_BOUNDARY`/`FALSE_POSITIVE`/`NEEDS_REVIEW`. Classify only — do not edit any file; fixers apply fixes later. | Diff (in scope) touches any Python source file or any `.ts`/`.tsx` file in the project's JavaScript/TypeScript package (and scanner finds >=1 candidates) |
| 9 | Code simplification | Registered subagent, dispatched by name: `code-simplifier` — it edits files directly | Once, after Step 6 exits clean — never here, see Step 7 |

Projects may register additional review dimensions of their own (e.g. a reviewer for prompt files the project maintains): add a row to this table following its pattern — a named registered subagent, a "Fires when" condition, and a severity-vocabulary row in Step 3 — and the dispatch rule below picks it up automatically.

**Never dispatch a dimension as a generic or `Explore` agent that loads a
specialist file — the per-dimension file-loading dispatch this skill once used
are gone, with no compatibility path.** Every dimension above is its registered
agent definition, dispatched by that exact name. Never pass a model argument:
model-tier choice belongs to the host and the model-assignment rule, not to
individual dispatches.

For dimension 7, run the scanner yourself before dispatching the classifier — it's deterministic, don't delegate it:

```bash
rg --files <touched .py paths from Step 1> -g '*.py' | sort > verify/antipattern_reports/code-review-fix-loop-files.txt
python3 .agents/scripts/extract_python_antipatterns.py --paths <same touched paths> --output verify/antipattern_reports/code-review-fix-loop-candidates.md
```

Scope both commands to exactly the touched paths from Step 1 — this is a per-diff pass, not a repo-wide hardening sweep. (`verify/` is gitignored; these scratch files never leak into the handoff diff.) If the scanner output contains zero candidate violations or reports no findings, short-circuit and skip dispatching the classifier subagent.

For dimension 9, run the scanner yourself before dispatching the classifier — it's deterministic, don't delegate it:

```bash
python3 .agents/scripts/extract_duplication_candidates.py --paths <same touched paths from Step 1> --output verify/duplication_reports/code-review-fix-loop-candidates.md
```

Scope to exactly the touched paths from Step 1 — the script itself expands to the bounded same-directory/module scan corpus, so this stays a per-diff pass, not a repo-wide sweep. If the scanner's output contains `## SKIPPED` or reports zero duplication candidates, treat dimension 9 as skipped for this iteration: short-circuit and do not dispatch the classifier (`verify/` is gitignored; these scratch files never leak into the handoff diff).

**Parallel dispatch mechanism** — this is the load-bearing part:

> Issue all dispatches in the same response and they run in parallel. Multiple dispatch calls in one response = parallel execution. One per response = sequential.

Issue every dimension in the table above whose "Fires when" condition holds against this iteration's scope — the always-on ones plus whichever conditional ones apply — as separate dispatch calls **within the same response turn**. Never write a fixed list of dimension numbers here: an enumeration silently freezes out every dimension added to the table afterwards, which is exactly how dimensions nine through twelve spent time being defined but never dispatched. Within a batch, do not spread the calls across multiple turns and do not wait for one to return before dispatching the next — see the concurrency cap below for how batches are bounded.

**Max N concurrent agents**, per `.agents/AGENTS.md`'s Agent Orchestration section — N from `.agents/config.toml` (`[worktrees] max_concurrent`, read via `agentic_workflows.worktree_capacity.load_max_concurrent_worktrees`; never hardcode it). With up to 8 applicable dimensions in the worst case, dispatch in batches of ≤ N — every call in one batch issued in the same response, and a queued batch starts as soon as a slot frees (one completion or one merge), never only after the whole running batch drains. That single-completion refill rides the notification-turn dispatch lifecycle — it exists where background dispatch makes a completion notification re-invoke you and the refill is evaluated on that wake (zcode-compat.md substitution 8, in `parallel-subagent-driven-development/references/`); under the same-turn dispatch above, no completion re-invokes you, so the cadence falls back to batch semantics.

This workflow previously exempted itself here, reasoning that its reviewers are read-only and non-overlapping so write contention cannot occur. That reasoning is sound about write contention and irrelevant to the cap: what the cap protects is API quota, and a batch of read-only reviewers consumes it exactly like writing ones. A real run hit 17 concurrent agents and exhausted the 5-hour quota — see `parallel-subagent-driven-development`'s own concurrency-cap note.

Every dispatch prompt must include: the path to this iteration's diff snapshot, `verify/review_reports/code-review-fix-loop-diff.md` (point at that file — never paste the diff inline, and never tell a reviewer to re-derive it with the Step 1 commands), an instruction that an empty or unreadable snapshot must be reported back as an explicit failure signal — never silently treated as "no findings" — an explicit read-only/no-edit instruction, and the dimension's own output-format expectation (from its own agent definition — don't restate it, just point at it).

The snapshot is the mechanical diff and nothing else.

### 3. SYNTHESIZE — normalize severities, judge every finding, partition into batches

Do this in the coordinator, after all dispatched reviewers return. Three independent things happen here, for every finding — this is always a full, thorough pass; there is no lighter-weight toggle.

**a. Normalize the vocabulary.** Each dimension reports severity in its own scheme. Map every finding to one of three buckets — Critical / Important / Minor — before doing anything else:

| Source dimension | Native vocabulary | → Critical | → Important | → Minor | Not a finding |
|---|---|---|---|---|---|
| `code-reviewer` | 0–100 confidence (only ≥80 reported) | 90–100 | 80–89 | — | <80 (already filtered by the agent) |
| `silent-failure-hunter` | CRITICAL/HIGH/MEDIUM | CRITICAL | HIGH | MEDIUM | — |
| `security-reviewer` workflow | CRITICAL/HIGH/MEDIUM (pattern table) | CRITICAL | HIGH | MEDIUM | — |
| `pr-test-analyzer` | 1–10 criticality per suggested test | 9–10 (Critical Gaps) | 7–8 (Important) | 5–6 (edge-case/Quality Issues) | 1–4 (nice-to-have — drop, don't fix) |
| `type-design-analyzer` | four separate 1–10 ratings per type, no single severity | any axis ≤3 | any axis 4–6 | any axis 7–8 (listed as a Concern) | axis 9–10 (Strength — not a finding) |
| `comment-analyzer` | named sections, no score | Critical Issues | Improvement Opportunities | Recommended Removals | Positive Findings |
| `py-antipattern-specialist` classifier | `FIX_IN_BATCH`/`LEGIT_BOUNDARY`/`FALSE_POSITIVE`/`NEEDS_REVIEW` | `FIX_IN_BATCH` where the escape hides a real runtime risk (e.g. masks a `None`/error path) | `FIX_IN_BATCH` otherwise (default) | — | `LEGIT_BOUNDARY`/`FALSE_POSITIVE` (drop); `NEEDS_REVIEW` (hold, don't auto-apply — see below) |
| `duplication-reviewer` (D-C) | `FIX_IN_BATCH`/`LEGIT_BOUNDARY`/`FALSE_POSITIVE`/`NEEDS_REVIEW` | `FIX_IN_BATCH` with 3+ occurrences or security/data-boundary code | ordinary `FIX_IN_BATCH` (default) | small/low-occurrence/low-risk `FIX_IN_BATCH` | `LEGIT_BOUNDARY`/`FALSE_POSITIVE` (drop); `NEEDS_REVIEW` (hold, don't auto-apply) |

Severity ordering (Critical → Important → Minor) decides batch and merge order in Steps 3e and 4. It does **not** decide whether to fix at all — that's the judgment pass below.

**b. Judge every finding against the actual diff before acting.** For every normalized finding, independently re-read the flagged `file:line` in the current diff (don't trust a finding you haven't confirmed against the code — verify before implementing, always) and sort into exactly one bucket:

- **Real defect** → queue it for the fix phase, tagged with its normalized severity.
- **Already handled** → the diff already addresses it (e.g. a later hunk fixes what an earlier hunk broke) — drop it, record why.
- **Wrong / overfit** → the reviewer misread the code, or the suggestion doesn't fit this codebase's actual contracts — drop it, record why. `NEEDS_REVIEW` classifications from dimensions 7 and 9 default here unless your own re-read resolves the ambiguity into a confirmed real defect.

**c. Dedupe across reviewers.** If two or more dimensions flag the same `file:line` for materially the same root cause, merge into one queued finding, keep the highest normalized severity across them, and note which dimensions concurred (independent concurrence is evidence, not noise — don't fix the same line twice). If two dimensions flag the same `file:line` for *different* root causes, keep both as distinct queued findings.

**d. `code-simplifier` is never processed here.** It has no findings list — it edits directly and narrates only significant changes. It does not participate in this step at all; see Step 7.

**e. Partition the confirmed findings into fix batches.** Map every queued real defect onto `ReviewFinding` from `agentic_workflows/review_fix_partition.py` — finding id, normalized severity, and the set of files it touches (a finding citing no file is rejected at the boundary, so resolve every finding's file set first). Read N once per run from `.agents/config.toml` via `agentic_workflows/worktree_capacity.py`'s `load_max_concurrent_worktrees` — never hardcode the number, and never write the config (N is human-only; agents never change it). Then call `partition_findings(findings, n, edited_files=..., repo_root=<integration worktree root>)`, passing as `edited_files` the union of files the prior iteration's fixers edited (empty on iteration 1) and as `repo_root` the integration worktree's root, so absolute finding citations canonicalize against it instead of failing fast. The partition module is I/O-free — the caller owns the config read; the module never reads `.agents/config.toml` itself. It returns:

- **At most N file-disjoint batches.** Any two findings touching the same file land in the same batch no matter how many batches remain (the union-find over file sets is the invariant that makes parallel fixers safe). More than N disjoint partitions merges tail-first by severity — the two lowest-value partitions fold together repeatedly until the count is ≤ N, so Critical slots survive longest; batch count never exceeds N. A single hot file yields exactly one batch regardless of N.
- **Deferred findings, severity-ordered.** Findings citing a file in `edited_files` — a file a prior batch already edited — cannot be scheduled this iteration without colliding with landed work (a cross-batch dependency), so the module returns them instead of batching them. Put them on the next iteration's finding list and record them in the Report. A deferral is a real defect the loop has not resolved: the loop may not exit clean while one remains unscheduled.

### 4. FIX — dispatch batch fixers in parallel, land by rolling merge

Never fix a finding yourself, and never invent a fixer agent type: the fix-phase fixer is `sdd-implementer`, dispatched by name with no model argument (a standard-capability model by its own definition).

Dispatch one `sdd-implementer` per Step 3e batch, all in the same response turn — at most N fixers concurrently, the same N the partition used (batch count is ≤ N by construction, so one wave always fits). Parallel file-disjoint batches are the point of this section, and the change is measured, not stylistic: the sequential one-finding-at-a-time in-place rule this replaces produced 13 sequential batches, $591, a ~15h tail, and 11 extra worktrees. The reversal is user-accepted and it reverses a stated skill rule (doc-conflict risk); partition correctness is load-bearing — two fixers sharing a file corrupt both batches' landings, so **a fixer edits only its own batch's findings and only its own batch's files, ever**.

**Worktree per fixer.** Each fixer works in its own worktree at the integration branch tip, acquired through `python3 .agents/scripts/worktree_acquire.py acquire` — it prints exactly one worktree path on stdout; exit 0 acquired, 1 refused (the on-disk cap is full; stderr names the holders and the two legal actions — wait for a slot, or land a batch so its merge frees one), 2 undecidable input (fail closed). The call takes `--name` (the worktree directory), `--branch` (the fixer's branch) and `--run` — pass the integration branch as `--run`, which is where a new `--branch` starts; `.agents/skills/parallel-subagent-driven-development/references/run-start.md` Step 1 item 1 shows the call shape. Reuse comes first: a worktree is created only when the script has no usable one to hand out and the cap allows — the script enforces this, so never create a worktree by hand and never edit `.agents/config.toml` to make room.

**Fixer brief.** Every fixer dispatch includes: its batch's findings (file:line, normalized severity, fix sketch), the diff snapshot path (never paste the diff inline), the acquired worktree path, the branch to commit on — one branch per batch, created inside the worktree, named after the batch (e.g. `review-fix-batch-<batch_id>`) — and the integration branch to sync to before fixing. The brief states the two hard rules: fix only this batch's findings and only this batch's files, and **commit the completed work to that branch before reporting** — an uncommitted batch cannot land (the durability precondition). The fixer runs the narrowest relevant checks for its touched files (Step 5's command table) before it commits, and reports with its definition's 6-line status card; the card's `Files Changed:` line is how the loop assembles the iteration's edited-file union.

**Land as each batch completes — rolling merge.** On a `Status: SUCCESS` card, merge the batch's branch into the integration branch — the same rolling dependency-order landing the parallel-subagent-driven-development workflow uses for groups (`.agents/skills/parallel-subagent-driven-development/references/landing-and-pr.md`), merged from the checkout that holds the integration branch. Batches of one wave are file-disjoint by construction and cross-batch dependencies were deferred, so there is no inter-batch dependency to order: when more than one batch is ready at once, merge in severity order — batch ids already follow severity. After each merge run Step 5's scoped checks, then release the worktree with the acquire script's `release` subcommand — its slot frees for a later batch or iteration.

**BLOCKED — fresh fixer, never a resume.** A `Status: BLOCKED` (or FAILED) card stops only that batch: resolve the blocker yourself when it is yours to resolve — escalate to the human only when it is not — then dispatch a **fresh** `sdd-implementer` on the same batch with the resolution written into its brief. Never resume the blocked agent. Sibling batches keep running throughout. Before every fresh dispatch, consult `decide_fixer_redispatch` in `agentic_workflows/review_loop_iterations.py` with the session ledger the iteration hook keeps at `logs/review_loop_iterations.json`: at most 2 fresh-fixer redispatches per batch per iteration; a refusal does not consume the count; persist the returned ledger around the dispatch. A third BLOCKED is final — escalate to the human, or defer the batch's remaining findings to the next iteration's finding list (recorded like any deferral). A fourth fixer is never dispatched.

### 5. VERIFY — scoped checks after every merge

After each batch merge, run only the checks relevant to that batch's touched files:

- Touched Python source or test files: the project's Python lint, type-check, and test commands scoped to the touched paths — **per merge**, where the project defines such tooling, because each narrows genuinely to the paths given.
- If the project has a JavaScript/TypeScript package (package.json at repo root or in a UI subdirectory) and the batch touched files under it: run its lint, typecheck, and test scripts — **once per wave of batch merges, not once per merge.** Run them after the last merge of the iteration's batch landings, over the union of every JS/TS path those batches touched. Because the type-check typically cannot narrow below the whole package, running it per batch pays the identical whole-package cost once per batch instead of once per wave — with up to N batches an iteration and up to `--max-iterations` iterations, that is the difference between a handful of whole-package type-checks per run and dozens.
- **The accepted cost, stated:** a frontend failure is attributed to a wave of batches rather than one batch's merge, and it still becomes a real finding on the next iteration's list exactly as a per-merge failure would. The batches of one wave are file-disjoint by construction (Step 3e), so the union of their JS/TS paths names every file the wave could have broken.

A failed check is a new real finding. The orchestrator never fixes: queue it onto the next iteration's finding list — its files sit inside that iteration's narrowed scope, since they are the prior fixers' edited-file union — and record the red check and the finding it became in the Report. Never carry a known-red merge silently.

### 6. LOOP — repeat until clean or the iteration cap

Go back to Step 1 with the now-updated diff (scoped against BASE, narrowed per Step 1's iteration rule). A narrowed iteration's REVIEW + SYNTHESIZE finding nothing in the "real defect" bucket does **not** exit the loop by itself — it is weaker evidence than a full pass finding nothing, since it never re-examined anything outside the files the previous iteration's fixers edited (Step 1). Stop looping when either:

- a full REVIEW + SYNTHESIZE pass over the *entire current scoped diff*, **dispatching every applicable dimension with no yield skips** (Step 2), returns nothing in the "real defect" bucket **and no deferral remains unscheduled** (everything was already-handled or overfit, and every earlier deferral has since been scheduled and fixed) — the diff is clean, proceed to Step 7. Concretely: when a narrowed iteration (2+) comes back clean, the loop does not exit there; it runs one more iteration, widened back to the full scoped diff (Step 1), and only *that* pass returning nothing lets the loop exit. If that confirming full pass turns up a new real defect instead, partition and fix it (Steps 3e–4) and keep looping — the iteration after a fix narrows again as usual, so this same confirm-before-exit rule applies again whenever a later narrowed pass comes back clean. Iteration 1 is already a full pass, so if it alone returns nothing and nothing was deferred, that single pass already satisfies this condition and no second confirming pass is needed. Or
- `--max-iterations` (default 5) is reached — stop even if real findings or deferrals remain, and report what's left instead of continuing unbounded. A run that stops this way has **not** earned the "clean" claim even if the most recent narrowed pass found nothing — say so explicitly in the Report (below): the confirming full pass never ran, so cleanliness was never actually established.

**This cap is enforced mechanically across Claude Code and ZCode.** `.agents/hooks/limit_review_loop_iterations.py` runs as a `PreToolUse` hook on the dispatch tool and denies the sixth dispatch of the iteration marker (`code-reviewer`) within one session on either host. It was added because the cap measurably did not hold on its own: 64 iterations across 6 sessions over seven days, a mean of 10.7, four sessions past 5, and only three of six reaching a clean exit. If a dispatch comes back denied, that is the cap firing — go straight to the Report and state that the run did not earn "clean". Do not route around it by dispatching a different dimension instead.

Two things the hook cannot do, so don't read more into it than it does. Nothing in a dispatch payload marks a run boundary, so it treats a 20-minute idle gap as the start of a fresh run — a genuine second run begun inside that window is refused, and a run that stalls past it silently gets a fresh budget. And it bounds the iteration *count* only: if each round of fixes keeps introducing new findings, the loop's inability to reach a confirming clean pass is the real defect and the cap merely bounds what that costs.

### 7. SIMPLIFY — code-simplifier, once, after a clean pass

Only after Step 6 exits via the clean-pass path (not the iteration-cap path — don't polish a diff that still has known real findings), dispatch the registered `code-simplifier` subagent by name, once, against the final scoped diff. Run it like a one-batch fix phase: acquire a worktree for it via the acquire script, sync to the integration branch tip, have it commit its edits to its own branch in that worktree, and land by the same rolling merge + scoped checks + release as Step 4. It edits directly and narrates only significant changes — there is no findings list to synthesize. Do not run it inside the loop (Steps 2–6): it edits/refactors autonomously rather than reporting findings, and running it mid-loop would cause thrash against findings that are about to change again anyway.

Include this calibration in the dispatch prompt: earn the suggestion — default to silence; if you're hedging on a reuse/simplification suggestion, drop it; the replacement must already exist in this repo or its current dependencies (adding a new dependency for a marginal reuse win is almost never justified); treat every leverage/reuse finding as advisory, never blocking — the implementer decides.

After it returns and its merge has landed, run Step 5's scoped checks once more against whatever it touched. If a check fails, queue the failure as a real finding and dispatch one fresh `sdd-implementer` fixer on it under Step 4's rules — do not re-enter the full defect loop and do not fix it yourself.

If `--max-iterations` was hit instead of a clean pass, skip this step entirely and go straight to Step 8.

### 8. HANDOFF — verify, report, stop

Run the project's verify command once (the Clean Handoff Gate, per `.agents/workflows/detailed-plan.md`) — exactly one full verification per run, at handoff, never per landing sequence and never per loop iteration; the per-merge scoped checks of Step 5 are the only verification that runs earlier. Report (see below) and STOP. The loop's git writes end at the baseline commit it required before FIX and the batch-branch merges it landed: it never pushes and never rewrites history — `push` stays hook-blocked, and the human reviews the integration branch and pushes when ready. The PR review is this run's remaining human checkpoint.

## Report

On stop (clean pass or iteration cap), report:

- iterations run, and per iteration: its scope (full sweep vs. narrowed to the previous iteration's fixer-edited union, per Step 1), the batches partitioned (count, any severity-order merges of disjoint partitions), findings fixed by batch, dimension, and severity, findings dropped and why (already-handled / overfit / `NEEDS_REVIEW` held), and findings deferred with where they went
- which of the 9 loop-time dimensions fired on this diff and which were skipped, and why — naming a **condition skip** (the dimension cannot apply) and a **yield skip** (it applied last iteration and produced no confirmed real defect) as the different things they are, and for a skip decided on a narrowed iteration, saying explicitly it was evaluated against that iteration's narrowed scope, not the whole diff, since the two can disagree (Step 2)
- the per-dimension yield across the run — confirmed real defects each dimension produced, per iteration — which is the record that makes the unmet A/B guardrail (Step 2) answerable later instead of permanently unmeasured
- fixer redispatches per batch, and any third-BLOCKED escalation or deferral (Step 4)
- whether the loop exited via Step 6's confirming full pass or hit `--max-iterations` before one ever ran — the latter has not earned the "clean" claim regardless of what the most recent narrowed pass found
- whether `code-simplifier` ran (Step 7) and, if so, a one-line summary of what it changed
- final verify command result (pass/fail, with failure detail if it failed)
- explicit statement that the integration branch carries the landed result — list the batch merges it contains — and that nothing was pushed; the human reviews the branch and pushes when ready

## Anti-patterns

- **Skipping Step 1's untracked-file check.** `git status --porcelain` is the only command that lists brand-new files; reviewing only the tracked delta on a diff that adds a new file misses the entire file.
- **Treating a missing or empty diff snapshot as a clean pass.** An unreadable `verify/review_reports/code-review-fix-loop-diff.md` is a coordinator-side failure to fix (Step 1), not evidence every reviewer looked and found nothing.
- **Exiting the loop after a narrowed pass alone, or with a deferral outstanding.** Step 6 requires one full REVIEW + SYNTHESIZE pass over the whole scoped diff to return nothing, and no unscheduled deferral, before the diff counts as clean — a narrowed pass finding nothing only proves the files a fix just touched are clean, not the rest of the diff.
- **Dispatching reviewers across multiple response turns.** One dispatch per response is sequential, not parallel — defeats the point of this step.
- **Yield-skipping a dimension on the confirming full pass.** The pass that lets the loop exit clean dispatches every applicable dimension; a yield skip there means "clean" was declared over a diff some dimension never looked at in that state (Step 2, Step 6).
- **Yield-skipping on a reviewer's raw count rather than confirmed defects.** A dimension whose every finding was dropped at Step 3b as already-handled or overfit yielded nothing, and one that reported nothing yielded nothing — treating a dropped finding as yield keeps a silent dimension alive for the whole run.
- **Yield-skipping the iteration marker.** Dimension 1 (`code-reviewer`) dispatches on every iteration no matter what it yielded before — the enforced iteration cap counts the marker's dispatches, and its table condition is "Always" — so a zero-yield previous iteration is never grounds for skipping it (Step 2).
- **Treating a never-ran dimension as yielded.** A dimension condition-skipped against last iteration's scope, or a dimension 7/9 scanner that short-circuited without dispatching its classifier, has no yield evidence: it dispatches the moment its condition holds again, and its prior skip stays a condition skip, never a yield skip (Step 2).
- **Dispatching a dimension as a generic or `Explore` agent that loads a specialist file.** Every dimension is its registered agent, dispatched by definition name with no model argument — the file-loading dispatches this skill once used are removed, not deprecated.
- **Queueing a finding without the Step 3 judgment re-read.** Trusting a reviewer's line number/description without confirming it against the live diff is exactly the failure mode Step 3b exists to prevent.
- **Fixing a finding yourself, or inventing a fixer agent type.** The fixer is `sdd-implementer`, dispatched with no model argument — the orchestrator synthesizes and lands, it never edits.
- **Letting two batches share a file, or a fixer edit outside its batch.** The file partition is load-bearing: same-file findings must co-batch, and a cross-batch dependency defers — it never schedules against landed work.
- **Dispatching a fourth fixer, or resuming a blocked agent.** At most 2 fresh-fixer redispatches per batch per iteration (`decide_fixer_redispatch`); a third BLOCKED escalates or defers — it never tries again.
- **Landing an uncommitted batch.** A batch's work must be committed to its own branch inside its worktree before its merge — the durability precondition that makes automatic worktree release safe.
- **Diffing later iterations against `HEAD` after batches have landed.** The loop's own merges move HEAD; only the BASE recorded at Step 1 keeps the reviewed surface from shrinking under the loop's feet.
- **Running `code-simplifier` inside the defect loop.** It edits autonomously; running it before findings have stabilized causes thrash.
- **Treating a `NEEDS_REVIEW` typing-contract or duplication classification as auto-confirmed.** It's a "needs a closer look" signal, not a `FIX_IN_BATCH` — don't silently promote it, for either dimension 7 or dimension 9.
- **Continuing past `--max-iterations` because "just one more pass would finish it."** Report what's left; don't run unbounded.
- **Pushing, or rewriting history.** The loop lands merges on the integration branch and stops there; `push` stays hook-blocked, and the human is the checkpoint that moves anything remote.
