---
name: technical-spike
description: Run a throwaway, real-data feasibility/accuracy/performance spike for a feature idea before committing to implementation. Infers framing (hypothesis, success bar, data source, candidate count) and confirms it in 1-3 lightweight questions, fans out parallel scenario discovery, then fans out one real verify/ script per credible candidate approach (or runs the single credible one directly) and synthesizes an honest verdict. Writes real executable scripts under verify/ using real production code and real project fixtures; never mocks; never proposes implementation code outside verify/; never deletes or cleans up spike scripts. Distinct from task-spec (requirements document, forbids running code) and architect/detailed-plan (plan-only, no execution).
disable-model-invocation: true
effort: medium
---

# Technical spike workflow

Turn the idea named in `$ARGUMENTS` — or, if `$ARGUMENTS` is empty, the idea already under discussion in the current conversation — into a throwaway, permanent script under `verify/` that answers one falsifiable question with real numbers, before anyone commits to an architecture or starts implementing.

## 1. Scope: what this answers, and what it hands off

This skill answers questions of the shape "should we build X" or "does approach A beat approach B on real data" — feasibility, accuracy, or performance questions that are cheapest to resolve by actually running something against real project data, not by reasoning about it on paper.

It is not the right tool for everything adjacent to it:

- A bug, regression, or unexpected behavior in code that already exists → use `.agents/workflows/root-cause-analysis.md`, not this skill. This skill spikes *new* ideas; it does not root-cause existing failures.
- Turning an accepted idea into a requirements/contract document (behavior, authorization, data semantics, acceptance criteria) → use `task-spec`. `task-spec` explicitly forbids running code; this skill exists specifically to run code.
- Reasoning through an architecture or implementation plan without executing anything → use `architect` or `detailed-plan`. Those produce plans and documents; this skill produces a script and real numbers.

When a spike here produces a clear verdict, the natural next step is usually one of those three — this skill says so explicitly in its final report (see Phase 3), but it never invokes them itself.

## 2. The `print()` exception

Production source is expected to follow the project's own logging conventions — never ad-hoc `print()` debugging. That convention does not govern `verify/`: spike scripts are throwaway, git-ignored artifacts that report results with plain `print()` statements — hypothesis in the docstring, real calls, `PASS`/`FAIL` lines, a summary tally. Every script this skill or its candidate-runners write follows that convention. This is not a violation of any project logging rule; it is this skill operating inside a recognized exception for the `verify/` sandbox, which never ships.

## 3. Phase 0 — Frame & Confirm

No subagents are dispatched in this phase. The lead does this work directly.

1. Read the idea from the ongoing conversation (or `$ARGUMENTS`). Grep `verify/*.py` docstrings for related prior spikes — this repo's scripts already cross-reference sibling scripts by filename in their own docstrings specifically to avoid re-testing the same thing, and this skill continues that culture. Also list existing `verify/*_spike.py` filenames that plausibly share this idea's slug (the same leading words before `_<candidate-label>_spike.py`) — this surfaces prior *rounds* of the same investigation, a distinct signal from "already answered," folded into step 2.
2. Build one confirmation question from whichever signals step 1 found, asked at most once:
   - If a prior spike already conclusively answers this question, surface it *first*, before drafting any new framing, and include: reuse/extend the existing script, narrow this spike to only what's untested, or proceed anyway.
   - If instead 2 or more same-slug prior scripts exist without a conclusive answer (an open, still-being-iterated investigation), add to the same question: continue as another round, or stop here and synthesize what the existing rounds already show, instead of running another live-billed battery.
   - If both signals fire, present all applicable options together in this one question. If neither fires, skip this question and proceed straight to step 3.
   Never ask this as two separate `AskUserQuestion` calls.
3. Draft one inferred-framing statement, in this order:
   - **Hypothesis** — a falsifiable claim, never a vague topic. ("Approach X parses malformed records with fewer than 2% failures across N runs" — not "test record parsing.")
   - **Success bar** — numeric when it can be inferred from the idea or prior art; otherwise a stated qualitative default, named explicitly as a default.
   - **Data source** — the spike fixture configured at `[spike] fixture` in `.agents/config.toml` (no bundled default: the config must name one for anything touching project data) for anything touching project content, or "no external project data needed" for a pure-computation idea. If the idea needs real data and no fixture is configured, that is a framing question for the user.
   - **Candidate count** — name the candidate approaches if 2 or more distinct approaches are already implied by the discussion; otherwise "one approach in view." This skill never *generates* candidate approaches — ideation is owned upstream by `task-spec-risk-analyst` (in the `task-spec` skill); a spike only counts and routes approaches already supplied.
   - **Baseline inclusion** — if the idea is framed as an improvement over something that already exists (shipped production behavior, or a prior spike), add the current/existing behavior to the scenario set as its own case, or run it as an implicit baseline candidate. This makes the Phase 3 comparison table show whether the new candidate actually beats what already exists, not just whether it works in isolation. When a baseline is included, its own multi-trial agreement measure (item 11) is the regression reference carried forward: whoever later adopts the winner must not regress against the baseline's agreement interval, not a single baseline run. That no-regression-on-adoption gate is promotion-time work (detailed-plan/TDD), not the spike's job.
   - **Live-call budget** — name the actual model or model-chain identifier each candidate will call (the project's named chain, or a literal model string) rather than just "production" or "lightweight," and state the rough live-call count the full battery implies (scenario count × candidate count), so cost is visible before anything is dispatched. No fixed numeric threshold — this is visibility, never a gate.
4. Confirm the framing with exactly **one** `AskUserQuestion` call: header `Spike framing`, options *Proceed as framed (recommended)* / *Adjust hypothesis or scope* / *Adjust success bar* / free text. Put the recommended option first, per this repo's standing `AskUserQuestion` convention.
5. Ask **at most two more** targeted questions, and only for a dimension that is still genuinely unresolved after step 4 (e.g. the success bar truly cannot be inferred, or candidate scope is still ambiguous). Ceiling: **3 `AskUserQuestion` calls total for Phase 0**, typical case: **1**.
6. Record the confirmed framing as a short block. Carry it verbatim into every delegation prompt in Phase 1 and Phase 2 — every scout and every candidate-runner sees the exact same hypothesis, success bar, data source, and candidate list the user confirmed.

## 4. Phase 1 — Parallel Scenario Discovery

Dispatch `technical-spike-scenario-scout` (`.agents/skills/technical-spike/agents/scenario-scout.md`) concurrently, in a single message. This specialist, and `technical-spike-candidate-runner` in Phase 2, are expected to be registered in this repository. If either is unavailable, state that once — it signals a registration gap, not an expected state — then continue with a built-in read-only Explore subagent or a focused substitute using the same brief. Do not abandon the workflow because a custom agent is missing.

- **2 instances by default.** A 3rd is added only when prior art is plausibly relevant to this spike (cap: 3 — tighter than the repo-wide concurrency cap N (`.agents/config.toml`, `[worktrees] max_concurrent`), because this workflow's scope is narrower; Phase 2's own cap of 4 is likewise inside it).
- This directly reuses the `BehaviorScenarioScout` multiplicity pattern already established in `.agents/workflows/detailed-plan.md`: one instance per scenario-space sub-domain, never a single agent guessing at every kind of case at once.
- Assign each instance exactly one sub-domain, never overlapping:
  1. Representative/happy-path real-data conditions.
  2. Boundary/edge/adversarial cases.
  3. *(Conditional, 3rd instance only)* Prior art — mining `verify/*.py` docstrings (and any project design docs your brief names) for what this idea already touches.
- Every instance is strictly read-only: it finds cases, it proposes nothing, it writes nothing.

Reconcile the returned scenarios into one light table — not `task-spec`'s 7-column ledger, this stays small:

| ID | Case | Why it matters | Evidence |
|---|---|---|---|

Dedup and merge by evidence. The lead curates this table itself: never average across instances, never simply take the loudest or longest report — the same Lead Synthesis Gate principle `.agents/workflows/detailed-plan.md` already applies: never manufacture artificial distinctions any more than that file lets you manufacture artificial parallel groups. When reconciling, bound the combined table by **t-way coverage (t≥2 floor, higher t where a feature's risk warrants it)** rather than the cartesian product — this is where the full scenario space is visible, so this is where the operative coverage bound is applied, not inside any single scout.

Surface this reconciled table — every scenario ID, its case, and its expected `PASS` signal — to the user as exactly **one lightweight, instantly-waveable confirmation** before Phase 2 (default on). It is NOT a blocking gate: a waved-through table proceeds straight to Phase 2 with no back-and-forth; it exists only so per-scenario pass criteria are seen before execution, not just in the final report. A `PASS` criterion shown here MUST be the exact one later reported against — never silently reinterpret it after the user waves it through. The one substantive exception still applies: if a scout surfaced something that makes the confirmed success bar unmeasurable as stated, resolve that in the same confirmation rather than reinterpreting the bar.

## 5. Phase 2 — Parallel Candidate Implementation

**Candidate-count rule** (concrete, not a matter of judgment call each time):

- **1 confirmed approach** → dispatch exactly one `technical-spike-candidate-runner` (`.agents/skills/technical-spike/agents/candidate-runner.md`) directly. Do not frame this as "parallel" — this is the explicit "never manufacture artificial alternatives just to force parallelism" case, the same principle `.agents/workflows/detailed-plan.md` states for parallel task groups.
- **2-4 credible approaches** → dispatch one `technical-spike-candidate-runner` per approach, concurrently, in a single message.
- **More than 4** → stop and ask one more question to narrow the candidate set first, rather than dispatching an oversized panel.

Each candidate tests the **full confirmed scenario set inside its own one script** — a "battery"-style script (multiple cases run in one file, a per-case `PASS`/`FAIL` line, then a summary tally). This is never one script per scenario. It keeps the agent-dispatch count bounded to the candidate count (at most 4 agents total in this phase), never multiplied by the scenario count.

Before dispatch, the coordinator pre-assigns each candidate's exact file path: `verify/<spike-slug>_<candidate-label>_spike.py`. The `_spike.py` suffix is this skill's own convention, distinct from the existing `_test.py` scripts, so that everything this skill has ever produced stays greppable as one set.

Each candidate's delegation package must include:

- the confirmed framing block from Phase 0, verbatim;
- the full scenario table from Phase 1 — every candidate tests the *same* scenarios, so results are comparable;
- what makes this specific candidate distinct from the others;
- its pre-assigned file path;
- the house-style checklist (below);
- the exact Output Contract fields it must return.

End-to-end instructions each candidate-runner follows: write its one assigned file → follow the house-style checklist → run it via `python3 verify/<file>.py` (never bare `python`) → capture the real output → return the Output Contract.

**Concurrency and shared-state guardrails**, grounded in real code rather than assumed:

- Call model/provider access through the project's existing adapter or router entry point — its retry handling for retryable provider errors then applies — rather than hand-rolling new retry logic on top. If the project has no such entry point, say so plainly in the script's docstring.
- Degrade to **sequential candidate dispatch** (never sequential scenarios within one script) when Phase 0 flagged heavy live-LLM call volume. Any residual rate-limit hit is reported honestly in that candidate's `deviations` field — never silently retried away into a cleaner-looking result.
- **No worktree isolation is needed** for git-file-collision reasons: each candidate writes exactly one distinct new file in an already git-ignored directory, so there is nothing for a worktree to protect. The real risk is different: a **shared non-git persisted store** — e.g. a project-level vector index, database, or any other on-disk cache living outside the git checkout entirely (which a worktree would not isolate anyway). The actual mitigation is to compute fresh, ad-hoc, in-memory results, and never mutate a persisted store. This is an explicit constraint on every candidate-runner (see its Verify-Only Constraint), not a worktree-isolation problem.

## 6. House-style checklist for `verify/` spike scripts

This checklist is embedded here once and referenced — never duplicated — by every candidate-runner delegation prompt.

1. **Docstring first** — a module docstring stating the hypothesis and why. Cross-reference sibling `verify/*.py` scripts by filename, and — when applicable — any project design docs the script's evidence draws on.
2. **Project config/credentials bootstrap — conditional, not universal** — when the script makes live API calls, bootstrap the project's configuration so credentials load, however the project does that (its config module, dotenv loader, or equivalent). Pure-computation scripts that touch no live service skip it.
3. **Real data by default** — read real inputs from the fixture configured at `[spike] fixture` in `.agents/config.toml` for anything touching project content; realistic, plainly-stated representative inputs for pure-computation ideas.
4. **Call real production code, never mock** — import and call the actual classes/functions directly. If the idea concerns code that doesn't exist yet, prototype the minimal real logic inline in the script itself — not a mock — and say so plainly in the docstring.
5. **Report with `print()`, no test framework, no project logger** — reuse the dominant idiom:
   ```python
   print(f"  is_complete={parsed.is_complete} (expected {case['expect_complete']}) [{'PASS' if complete_ok else 'FAIL'}]")
   ...
   print("=== Summary ===")
   n_pass = sum(r["overall_pass"] for r in results)
   print(f"  {n_pass}/{len(results)} cases fully passed.")
   ```
   or an explicit verdict string when one overall call fits better than a per-case tally.
6. **Performance/latency — rarely has local precedent, add the minimum** — most existing spike scripts measure no elapsed time. When the spike is actually about performance, wrap the operation under test with `time.perf_counter()`, print per-scenario elapsed time alongside `PASS`/`FAIL`, and report an aggregate (mean/p95) — nothing heavier than that.
7. **Report ambiguity honestly** — if results genuinely disagree, print that plainly rather than forcing a false `PASS`/`FAIL`.
8. **No regression across iterations** — every re-run of a candidate script during debugging tests the full confirmed scenario set, never a narrowed subset: every scenario must carry a real observed result in the final report, sourced from a fresh call or a valid same-script cache hit (item 9) — never silently dropped. If an edit that fixes one scenario breaks a previously-passing one, report that regression honestly in `deviations` rather than dropping the scenario or silently re-baselining.
9. **Cache real responses across debug re-runs — never fabricate, only skip re-billing** — for any live model call, first check a local cache before calling out: key `sha256(json.dumps({"model": model, "request": request_payload}, sort_keys=True))`, where `request_payload` MUST include every scenario-specific field that shapes the real request (full prompt/message content, tool schema, sampling parameters) — never a partial payload, since an incomplete key can make two genuinely different requests collide. Store at `verify/.spike_cache/<script-slug>/<hash>.json`, where `<script-slug>` is this script's own pre-assigned filename stem (Phase 2's `<spike-slug>_<candidate-label>_spike`). On a hit, deserialize and return the cached value as-is — it is always a real response this same script already captured; never hand-edit a cache file, and never reuse one scenario's cached entry for a different scenario's request. On a miss, make the real call, then write the response before returning it. A cache-read failure (missing, corrupted, unreadable, or a validation error when reconstructing a typed response) is a miss, not an error: fall back to a live call and record the fallback in `deviations`.

   **Mandatory exception:** a scenario is cache-exempt — always a fresh live call, cache never read or written — whenever (a) its PASS signal requires issuing the identical request more than once and comparing results, OR (b) it is a multi-trial variance sample under item 11 (any nondeterministic scenario a verdict depends on). In both cases every trial, including the first, is fresh: caching them would hide the exact variance being measured. When judging whether a scenario qualifies, read what the PASS signal requires you to *do*, not just its topic label.

   **The cache directory holds only content-addressed response files matching `<hash>.json`** — never scratch notes, alternate drafts, or debug logs. It is not covered by this skill's "no cleanup, ever" rule for spike deliverables (§8): a human may delete `verify/.spike_cache/` at any time to force fresh calls, and you must never delete it yourself either — leave it alone once written.

   ```python
   import hashlib
   import json
   from pathlib import Path

   # Replace <script-slug> below with this script's own filename stem, e.g. "my_idea_candidateA_spike".
   CACHE_DIR = Path("verify/.spike_cache/<script-slug>")

   def cached_call(model: str, request_payload: dict, live_call, deviations: list[str]):
       key = hashlib.sha256(
           json.dumps({"model": model, "request": request_payload}, sort_keys=True).encode()
       ).hexdigest()
       cache_file = CACHE_DIR / f"{key}.json"
       if cache_file.exists():
           try:
               return json.loads(cache_file.read_text())
           except (OSError, ValueError) as exc:
               deviations.append(f"cache read failed for {key}, falling back to a live call: {exc}")
       response = live_call()
       CACHE_DIR.mkdir(parents=True, exist_ok=True)
       cache_file.write_text(json.dumps(response, indent=2))
       return response
   ```

   Adapt the serialize/deserialize step to whatever response object your script's call returns (e.g. a `.model_dump(mode="json")`-style serialization and matching constructor/validation call for a pydantic-style model); if reconstructing a typed model can raise its own validation error on a corrupted cache file, catch that too and treat it the same as the read failure above.
10. **Reuse the project's prompt-cache utility for a repeated stable prefix** — if your script sends the same large stable prefix (e.g. a production system prompt or template) across many scenario/candidate calls to a model, wrap the stable blocks with the project's existing prompt-cache utility before calling the model adapter, where the project ships one. This is a pointer to already-shipped production code, not new design; such a utility should no-op safely for models and prefixes below its own supported threshold, so no extra branching is needed in the spike script. If the project has no such utility, skip this item and say so in `deviations`.
11. **Multi-run any nondeterministic scenario a verdict depends on — never trust one sample** — when a scenario's PASS signal measures nondeterministic output (LLM/agent output, or any value that can vary run-to-run) that the verdict rests on, run multiple independent **trials** and report an **agreement measure** for this candidate, never a single sample. Increase `n_trials` until the agreement measure stabilizes (added trials no longer change the verdict) OR a setting-aware soft ceiling is reached — roughly **3 trials** for a temperature-0 + fixed-seed call, up to **~10** for default sampling. These counts are research-cited starting points, not hard constants (see `.agents/rules/no-overfitted-fixes.md`); a scenario whose PASS signal is explicitly about variance may deliberately exceed the ceiling. Do NOT conclude "A beats B" on a delta inside the **noise floor** (~2–3 percentage points for benchmark-style pass rates; a judgment read of what the PASS signal actually measures for anything else — for an open-ended, non-benchmark judgment there is no percentage-point floor, so report agreement honestly and flag the comparison as unverified rather than inventing a threshold). **The N-trial variance loop is structurally cache-exempt: it never reads or writes `verify/.spike_cache/` for any trial, including the first** — otherwise identical-request trials collapse to one cached sample and the agreement number is a fabrication of the cache. Cross-candidate comparison and the terminal "indistinguishable" verdict are the Phase-3 lead's job (§7), not a candidate-runner's.

## 7. Phase 3 — Synthesis & Verdict

The lead does this work directly; no subagent is dispatched for synthesis.

Build one comparison table — rows are scenarios, columns are candidates (a single column when there is only one candidate) — populated **only** from each candidate's returned `per_scenario_results`. The lead never re-executes or re-derives anything itself; it only reconciles what the candidate-runners actually observed.

The verdict takes one of four honest shapes. The lead — the only actor that sees every candidate — computes any cross-candidate A-vs-B comparison here from the returned per-candidate multi-trial records (it never re-executes, per above):

- **Clean winner** — one candidate meets or exceeds the confirmed success bar on materially all scenarios (or it is the only candidate tested). State the verdict plainly and name the winning script as evidence.
- **No winner** — none of the candidates meets the bar. Say so plainly; report the real gap and what would need to change, rather than forcing a false pass. This continues the `verify/` convention of reporting genuine disagreement honestly instead of manufacturing a verdict.
- **Ambiguous/split** — e.g. candidate A wins on accuracy, candidate B wins on latency. Report the real per-scenario trade-off explicitly. Never average results together into a false single winner.
- **Indistinguishable** — for a multi-trial scenario (item 11), the A-vs-B delta sits within the **noise floor** even at the trial ceiling. Report "indistinguishable," never a forced winner; the decision then reverts to a non-empirical criterion (cost, simplicity) or becomes implementation discretion.

The final report contains, in order:

1. the confirmed hypothesis and success bar, recapped verbatim from Phase 0;
2. the scenario table from Phase 1;
3. the candidate comparison table;
4. the plain verdict, in one of the three shapes above;
5. every script path produced — all of them remain in `verify/`, with no cleanup, ever;
6. one paragraph of honest caveats (sample size, live-API non-determinism, anything already flagged in a candidate's `deviations` or `confidence` fields);
7. a provenance stamp: for each candidate, the model-chain identifier it called (from that candidate's runner output — candidates may use different chains) and the measurement date, because agreement numbers and the noise-floor threshold are model- and time-sensitive on a permanent, never-deleted artifact;
8. a suggested next step.

**The suggested next step is advisory only.** This skill never auto-invokes another skill and never writes to `docs/decision-notes/` itself.

- Consequential decision + clear winner → suggest `deliberation` (to produce a tracked ADR citing the winning script as evidence) and/or `task-spec`/`architect`.
- Small decision + clear winner → suggest going straight to implementation.
- No winner, or ambiguous/split → suggest narrowing the scope and re-spiking, or note that the honest ambiguity itself may be worth a `deliberation` entry.

**The brief is written by a dispatched `document-writer`, never by the lead:** `verify/<spike-slug>_brief.md`, mirroring the final report above, composed and written by `.agents/specialists/document-writer.md`, which returns only that path and the written file's byte size. The lead records the path and does not read the body back. Its first two lines are exactly:

```text
Derived-from-commit: <full sha>
Written: <YYYY-MM-DD>
```

That syntax is fixed, because `.agents/scripts/spec_staleness.py` parses `Derived-from-commit:` to anchor every later freshness check. Write to a 20,000-character target and never trim, thin, or drop a real finding to reach it, because that number is a writing budget and never a ceiling on what the record may carry.

The brief persists next to the scripts it references, continuing this repo's existing paper-trail culture, fully git-ignored, never deleted. Every candidate script stays owned by the candidate-runner that wrote it (single-writer rule per artifact, mirroring `task-spec`'s single-writer rule for its specification document).

## 8. No cleanup, ever

Every script this skill writes — every candidate-runner's `_spike.py` file and the `document-writer`'s `_brief.md` — is a **permanent artifact**, exactly the same status as every other script in `verify/`. This skill never deletes anything it or a candidate-runner wrote, regardless of whether the spike's result was a clean win, a clear loss, or genuinely ambiguous. A negative result is not a reason to clean up; it is itself the recorded evidence for the verdict.
