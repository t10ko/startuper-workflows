---
name: task-spec
description: Create or refine one task/ticket-specific, repository-grounded, engineering-ready specification through the AskUserQuestion UI, focused decision workshops, parallel read-only specialists, and adversarial readiness audits. Covers behavior, authorization, data semantics, contracts, and material technical design decisions. Never implements, and never writes an implementation task plan itself; with the opt-in `--to-plan` flag it hands an approved specification straight to `detailed-plan` in the same session instead of stopping with a command to paste.
disable-model-invocation: true
effort: high
---

# Task specification and design workflow

Turn the task represented by `$ARGUMENTS` into a precise specification for one coherent change.

The goal is not merely a long requirements document. The goal is to remove the behavioral, security, data, contract, and high-cost technical ambiguities that would otherwise be discovered during implementation.

Parse and remove these optional flags before interpreting the task:

- `--workshop`: begin in intensive decision-workshop mode.
- `--requirements-only`: produce a behavior-and-contract specification, but do not choose physical data structures or other engineering design alternatives. Report remaining design questions separately.
- `--design`: force the engineering-design layer after behavioral requirements are clear.
- `--lean`: keep orchestration single-agent unless one focused specialist is clearly necessary.
- `--parallel`: force the discovery and audit fan-outs even when the task looks trivial or small.
- `--workflow`: use a Claude Code dynamic workflow for eligible read-only discovery and audit checkpoints when available; otherwise fall back to parallel subagents.
- `--to-plan`: once the user has answered yes to the final approval question, continue straight into `detailed-plan` in this same session instead of stopping with a command to paste. It never skips, weakens, or pre-answers that approval question. It trades the compaction the default handoff buys for one fewer typed command, so the planning phase runs on top of the whole specification conversation rather than on a fresh context. Prefer the default when the questioning loop was long. Incompatible with `--requirements-only`, which cannot reach the readiness a plan needs.

Without `--requirements-only` or `--design`, use **adaptive mode**:

1. Fully resolve behavioral requirements, authorization, data semantics, external contracts, and acceptance criteria.
2. Run an implementation-readiness simulation.
3. Resolve a technical design decision inside the specification only when leaving it open would force an implementer to invent important semantics, create substantial rework, or introduce material correctness, security, migration, performance, or operational risk.
4. Leave small, local, reversible coding choices to implementation discretion.

Without an orchestration flag, parallelize substantial or high-risk work, but avoid agent overhead for tiny, well-defined changes.

If `$ARGUMENTS` is empty after removing flags, use the task already described in the current conversation. Ask for a task description only when neither source contains one.

This workflow remains active across subsequent turns. Continue updating the same specification after each answer until it is ready or the user stops.

Treat the saved specification document as the source of truth across turns. Re-read it from disk at session start, immediately after a compaction, and immediately before each audit or readiness checkpoint — and then only the sections about to be touched or audited. Between those points this coordinator is the document's only writer (see "Single-writer rule"); its own edit record is authoritative, so do not re-read merely to reconstruct what it just wrote itself. On a long workshop or audit cycle, suggest a compaction or handoff point once conversation history has grown well beyond what the saved document already captures.

## Hard boundaries

- Produce or update exactly one Markdown document for the current task.
- The document may contain both a behavioral specification and a clearly separated engineering-design section.
- Do not modify application code, tests, configuration, dependencies, schemas, migrations, branches, worktrees, commits, or pull requests.
- Do not create an implementation task breakdown, file-by-file coding plan, estimates, or executable code. `--to-plan` does not relax this: it hands control to `detailed-plan`, which writes its own separate plan document, and this workflow still writes only the specification.
- The **Implementation execution guidance** section (§11, §22) is the one exception that names parallel-safe groupings and their complexity signals for whoever executes next — never a model or thinking tier, which planning owns. It stays at requirement/flow/data-ID granularity and must never include file paths, function names, or a step-by-step task list — that decomposition remains implementation planning's job.
- Read code, tests, schemas, migrations, contracts, tickets, and documentation only to discover current behavior, constraints, and established patterns.
- Never turn an incidental implementation detail into a requirement merely because it exists today.
- Do not specify class names, function names, source-file layout, framework plumbing, or line-by-line algorithms unless an external compatibility constraint makes one of them part of the contract.
- A data-model outline, API/event contract, transaction boundary, storage choice, migration strategy, or architectural decision is allowed when the workflow's design rules say it is material. DDL, migration scripts, complete endpoint code, and implementation tasks are not allowed.
- Never claim that every theoretically possible case has been found. Cover every materially distinct behavior and explicitly record residual uncertainty.

**Four levels of questions** — the classification framework every discovered question must be sorted into before deciding whether to ask it — lives at `.agents/skills/task-spec/references/questioning-protocol.md` — read it when a discovered question needs classifying; every later step's use of Level 1-4 depends on it.
**Orchestration and parallelism** — the coordinator's multi-agent dispatch mechanics (single-writer rule, specialist roster, delegation context package, fan-out/fan-in, checkpoints, dynamic-workflow mode) — lives at `.agents/skills/task-spec/references/orchestration-and-parallelism.md` — read it when dispatching, delegating to, or coordinating any specialist subagent or workflow, or making any fan-out/fan-in or checkpoint decision.
**Mandatory structured question UI and conversation modes** (clarification mode, decision-workshop mode) live at `.agents/skills/task-spec/references/questioning-protocol.md` — read it when you are about to ask the user a question, before opening `AskUserQuestion` or choosing between clarification and decision-workshop mode.
## 1. Resolve the task source and document path

Use this order:

1. Update an explicitly named Markdown specification.
2. Reuse an existing task specification matching the ticket or task.
3. Follow the repository's established convention such as `docs/specs/`, `specs/`, or `docs/tasks/`.
4. Otherwise create `docs/specs/<ticket-or-short-slug>.md`.

Preserve a ticket identifier in the filename when available. Read accessible ticket contents rather than asking the user to repeat them.

When reusing an existing specification, check its `Updated` date and cited evidence against the current repository state for staleness. If material evidence has changed, re-run `task-spec-discovery-scout` scoped to that evidence and treat any `Confirmed` claim the fresh evidence contradicts as a new Level 1 or 2 question rather than carrying it forward unchanged.

**Grounding freshness** — before reading any grounding artifact body, follow `.agents/references/grounding-freshness.md`, the single owner of the staleness-check protocol and of what each exit code obliges you to do.

## 2. Ground the work in the repository

Inspect only relevant parts of:

- task or ticket text;
- `AGENTS.md` and project instructions;
- product, domain, architecture, security, and data documentation;
- current behavior in code;
- tests that reveal contracts and edge cases;
- schemas, migrations, models, indexes, and query patterns;
- public APIs, events, CLI contracts, and UI behavior;
- related permissions or policy code;
- similar completed features, and any project-defined reuse registry or component/pattern convention that new construction should be checked against first;
- the project's own documented hard invariants — rules the project states as non-negotiable — recording any conflict between the requested task and a stated invariant as a Level 1 question rather than resolving it silently;
- whether the task bundles multiple materially distinct concerns that would be clearer as separate specifications — different actors, data domains, or acceptance criteria that don't share one coherent flow — and split scope accordingly before drafting.

Separate:

- confirmed current behavior;
- requested behavior;
- accepted user decisions;
- assumptions;
- open requirement or design decisions.

Do not assume current behavior is desired behavior.

### Parallel discovery checkpoint

Unless `--lean`, or genuinely trivial and `--parallel` was not supplied:

1. Run `task-spec-discovery-scout` (mandatory: repository grounding, and failure-class analysis whenever the task is a defect — see §5b).
2. Run `task-spec-contract-analyst` whenever the task alters flows, authorization, data persistence, UI surfaces, or LLM call sites.
3. Run `task-spec-risk-analyst` whenever the task touches dependencies, security boundaries, concurrency, cost budgets, or engineering-design decisions.

**The scout writes `docs/specs/grounding/<spec-slug>.md` itself** and returns a bounded card naming that path. That file is the pipeline's shared grounding artifact: file inventory, symbol map, and the excerpts the scout actually used. Its first two lines are exactly:

```text
Derived-from-commit: <full sha>
Written: <YYYY-MM-DD>
```

That syntax is fixed, because `.agents/scripts/spec_staleness.py` parses `Derived-from-commit:` to anchor every later freshness check. Write to a 20,000-character target and never trim, thin, or drop a real finding to reach it, because that number is a writing budget and never a ceiling on what the record may carry.

The coordinator records the path and does not read the body. `detailed-plan`'s Wave 1 and the implementers read it instead of re-reading source, and every later stage verifies against source only for the specific claim under test. Measurement history: design-notes.md §The grounding artifact file-read measurement.

Run `task-spec-discovery-scout` first and wait for it. Then select the
remaining relevant specialists from the list above and launch those
concurrently, giving each one the scout's `Confirmed` findings for its own
lens in the delegation context package's "relevant repository areas already
identified" slot. Require each to reconcile its lens against that record
before reading anything else, and to read source only to verify a claim the
record makes, to settle a contradiction against it, or to cover a surface the
scout did not reach — not to rebuild a model that already exists.

Launching all of them at once instead makes five to seven agents read the
same area simultaneously, none able to see what the others found. The
reconciliation wording above is the contract this workflow already applies at
the behavioral audit checkpoint; this applies it one stage earlier, where the
duplication actually originates.

The scout's findings are one agent's reading, not ground truth. An analyst
whose own lens contradicts the record reports the contradiction rather than
deferring to it.

Synthesize one evidence model containing:

- current behavior and constraints;
- actor and authorization model;
- conceptual data and lifecycle model;
- state transitions and flows;
- failure and consistency risks;
- external contract implications;
- material engineering design choices;
- contradictions and unknowns.

Do not ask the first substantive question until fan-in completes.

## 3. Write the initial draft before extended questioning

**A document body over 8,000 characters is written by a dispatched `document-writer`** (`.agents/specialists/document-writer.md`), which returns only the path it wrote and that file's byte size; the orchestrator then reads back only the sections it must act on. The threshold is exclusive: a body of exactly 8,000 characters is written by the orchestrator itself, and only a body above that reaches the writer. It decides who writes the document, never how long the document may be, and no real finding is ever trimmed, thinned, or dropped to land on either side of it.

Create a useful draft from known facts. Apply low-risk defaults only when they are conventional, supported by the repository, and do not materially affect behavior, security, data semantics, compatibility, or operations — distinguish a structural repository convention (a pattern the codebase enforces broadly) from the shape of one example's content, which does not by itself establish a convention. Record each under **Assumptions**.

Use the following structure; the full template lives at `.agents/skills/task-spec/references/spec-template.md` — read it when drafting the initial specification. Omit a section only after checking it is genuinely irrelevant; do not write placeholder `N/A` sections.

Sections:

1. Problem and intended outcome
2. Scope
3. Current behavior and repository constraints
4. Actors and authorization
5. Behavioral requirements
6. Flows
7. States, transitions, and invariants
8. Data and persistence contract
9. Inputs, outputs, validation, and error contract
10. External contracts and dependencies
11. Concurrency, idempotency, and partial failure
12. Edge cases and boundary conditions
13. Quality attributes
14. Migration, rollout, and compatibility constraints
15. Engineering design decisions
16. Acceptance criteria
17. Traceability
18. Assumptions
19. Open questions
20. Decision log
21. Implementation discretion
22. Implementation execution guidance
23. Readiness assessment

Writing rules:

- Use stable IDs.
- Make every `MUST` atomic, observable, and testable.
- Use one canonical term per concept.
- Replace vague adjectives with verifiable criteria when relevant.
- Do not invent targets or legal requirements.
- Keep assumptions separate from decisions.
- Do not bury permission or data rules only in prose; use the required matrices and subsections.
- Every major requirement must have acceptance coverage.
- State the underlying concept a fixed pattern, threshold, or rule enforces, not just the shape of the current example; flag it when it is unverified against the system's known input diversity.
- Give acceptance criteria genuine case and boundary diversity; do not restate the same case under different labels.
- State each acceptance criterion's verification method — unit test, integration test, or manual/exploratory check.

**4. Authorization analysis** — mandatory when a resource is involved — lives at `.agents/skills/task-spec/references/authorization-analysis.md` — read it when the task involves a resource that needs an authorization decision.
**5. Data and persistence analysis** — mandatory when data persists — lives at `.agents/skills/task-spec/references/data-persistence-analysis.md` — read it when the task involves data that persists.
**5a. UI and frontend analysis** — mandatory when the task has a UI or frontend surface — lives at `.agents/skills/task-spec/references/ui-frontend-analysis.md` — read it when the task has a UI or frontend surface.
**5b. Failure-class analysis** — mandatory when the task is a defect — lives at `.agents/skills/task-spec/references/failure-class-analysis.md` — read it when the task under specification is a defect.
## 6. Extract materially distinct flows

Build an internal model from:

`actor × permission × entry point × starting state × action × input class × dependency condition × timing/repetition × outcome`

Find distinct outcomes rather than generating a combinatorial list. Merge cases with identical required behavior. Bound the flow set by **t-way coverage (t≥2)** — cover the distinct interactions among actor/state/input/dependency conditions, not their cartesian product — rather than enumerating every combination.

At minimum consider when relevant:

- primary success and alternate valid paths;
- missing, malformed, duplicate, minimum, maximum, and adjacent-boundary inputs;
- unauthenticated, unauthorized, revoked, cross-tenant, and field-redaction cases;
- empty, pending, stale, unavailable, degraded, and offline states;
- dependency timeout, rate limit, malformed response, delayed response, and outage;
- failure before mutation, failure during mutation, failure after mutation, and unknown outcome;
- retry, recovery, cancellation, rollback, and compensation;
- duplicate requests, idempotency, races, stale writes, concurrent edits, and reordered events;
- expired, deleted, archived, restored, and invalid transitions;
- old/new clients, existing data, mixed-version states, and rollback;
- loading/skeleton, optimistic update and its rollback, and in-progress/streaming states, when the task has a UI surface.

For every error/failure class, define:

- trigger;
- externally visible result;
- state afterward;
- whether the action is retryable;
- recovery path;
- consistency requirement;
- user/operator signal when relevant.

## 7. Coverage scan and question prioritization

Maintain an internal coverage map with `Clear`, `Partial`, `Missing`, or `Not relevant` for:

1. problem, outcome, scope, non-goals, and unchanged behavior;
2. actors, identities, operations, ownership, tenancy, and permission matrix;
3. domain terminology and business rules;
4. entities, identity, cardinality, lifecycle, retention, and source of truth;
5. states, transitions, invariants, primary, alternate, error, and recovery flows;
6. inputs, boundaries, validation, outputs, and error contract;
7. external interfaces, events, dependencies, and partial failure;
8. consistency, transaction semantics, concurrency, duplication, idempotency, and conflict behavior;
9. security, privacy, sensitive fields, abuse, audit, and disclosure behavior;
10. accessibility, localization, performance, reliability, capacity, observability, and compatibility;
11. migration, backfill, rollout, mixed-version, and rollback constraints;
12. material engineering design decisions and alternatives;
13. acceptance coverage, traceability, assumptions, contradictions, and unresolved placeholders;
14. project-documented hard invariants and any conflict with the requested task;
15. UI and frontend coverage: keyboard, focus, screen-reader, color-contrast/motion, and component/template reuse;
16. asynchronous and background-job execution model: spawn semantics, buffering or chunking, and detached-versus-awaited behavior;
17. generalization basis for any pattern, threshold, or rule the specification relies on;
18. cost and third-party content rights/licensing implications;
19. for a defect: the abstract broken contract, its sibling instances, and the in-scope/out-of-scope decision for each.

For every gap:

1. Classify it as Level 1, 2, 3, or 4.
2. Rank it by:

`impact × uncertainty × cost of a wrong assumption × irreversibility × coupling`

3. Ask only if the answer materially affects behavior, security, data semantics, contracts, acceptance, migration, or a high-cost design choice.
4. Resolve Level 4 locally during implementation; do not question the user.

## 8. Clarification and decision loop

**The clarification and decision loop** — question selection by level, the empirical hand-off to `technical-spike`, the spike-verdict crosswalk, the post-answer update sequence, and the fatigue and stop rules — lives at `.agents/skills/task-spec/references/clarification-and-decision-loop.md` — read it when taking the highest-ranked unresolved item into clarification or decision-workshop mode.

**9. Requirements and design quality audit** lives at `.agents/skills/task-spec/references/quality-audit.md` — read it when auditing requirements and design quality, unless `--lean` was supplied.
**10. Implementation-readiness simulation** — the main defense against discovering important questions only after coding begins — lives at `.agents/skills/task-spec/references/readiness-simulation.md` — read it when behavioral requirements are stable and you are running the implementation-readiness simulation.
## 11. Implementation execution guidance

After the implementation-readiness simulation, synthesize one advisory section from evidence already collected — do not dispatch a new specialist for this.

Build **parallel execution groups** by comparing, across requirements, flows, and data changes:

- shared tables, entities, or storage from the data-analyst's model;
- shared permission-check paths from the authz-analyst's model;
- shared files, modules, or contracts from the repo-scout's findings;
- shared flows from the flow-analyst's model;
- hard ordering constraints from Engineering design decisions and Migration/rollout (e.g., a migration that must land before the flow depending on it).

Label each group **Independent (parallel-safe)** or **Sequential (must follow \<group\>\[, \<group\>...\])** — a group that genuinely gates on more than one other group names every one of them, comma-separated, and starts only once all of them have merged — with a one-line reason naming the shared resource or ordering constraint. Merge groups only when the coupling is real; default to more, smaller groups over one large one. For a small spec where every requirement is tightly coupled or there's only one unit of work, say that plainly in one line instead of manufacturing artificial groups.

### Critical path & concurrency rules for execution guidance
- **Critical Path Minimization**: Identify the longest sequence of dependent groups. Never bundle non-blocking requirements (cleanup, secondary docs, peripheral flows) into a group that gates downstream groups.
- **Wave 0 Pre-Flight Configuration Bootstrap**: When multiple groups only share configuration additions (`settings.toml`) or base schemas/DTOs, designate those setup tasks as a Wave 0 pre-flight bootstrap to land on the integration branch first. This prevents false serialization of otherwise independent tracks.
- **Concurrency Cap Saturation**: Shape independent groups to saturate available concurrency slots up to the configured cap N (`.agents/config.toml`, `[worktrees] max_concurrent`), queuing additional groups in batches of ≤ the configured cap.

Record one line of **complexity signals** per group — risk-analyst findings, readiness-critic findings, and engineering-design complexity — and stop there.

**Never assign a model or a thinking tier in a specification.** A specification names no model anywhere, in any wording — `.agents/rules/model-assignment.md` is the single owner of every model choice, and an implementer runs a standard-capability model under it without exception. Thinking tiers are owned separately by `.agents/skills/detailed-plan/references/execution_grouping.md` §2 — read it when you need to know which tier a group will run at, never to state one here, since §2 reads these signals to decide them itself. Either value written here would be a second writable store — a defect the moment it is written, not once the two diverge (`.agents/rules/single-source-of-truth.md`).

This section is advisory. It does not gate `Requirements ready` or `Engineering-ready`, and it never becomes a file-by-file task list — that decomposition remains the next planning step's job.

## 12. Completion states

Set:

### `Readiness: Requirements incomplete`

When any Level 1 or 2 blocker, permission blocker, contradiction, or major acceptance gap remains.

### `Readiness: Requirements ready`

When:

- behavior, scope, permissions, data semantics, contracts, flows, failures, UI and accessibility requirements (when applicable), and acceptance criteria are complete;
- no Level 1 or 2 blocker remains;
- the behavioral audit passes;
- any remaining Level 3 decisions are explicitly listed;
- only safe Level 4 discretion remains unlisted or documented.

This is the maximum readiness in `--requirements-only` mode.

### `Readiness: Engineering-ready`

When, in adaptive or `--design` mode:

- all Requirements-ready conditions pass;
- material Level 3 decisions are accepted or explicitly marked as intentionally deferred with a safe boundary;
- data storage, transaction, contract, integration, migration, and operational choices are sufficiently constrained where relevant;
- the implementation-readiness simulation finds no unresolved blocker.

`Engineering-ready` does not mean code was planned or implemented.

Before moving `Status` past `Draft` or `Ready for review`, ask one explicit final `AskUserQuestion` — "Approve this specification for handoff to implementation?" — and set `Status: Approved` only on an explicit yes; otherwise keep `Status: Draft` or `Ready for review` as appropriate. Reaching `Readiness: Engineering-ready` never implies approval by itself.

## 13. Completion report & Planning Handoff

When questioning ends, respond briefly with:

- specification path;
- status and readiness;
- mode used;
- number of accepted decisions;
- whether authorization, data, and readiness audits ran;
- number of parallel execution groups identified, or `none`;
- unresolved Level 1/2 questions, or `none`;
- unresolved material Level 3 decisions, or `none`;
- significant residual risks or coverage limitations;
- a reminder that `Readiness` reflects audit completeness only, not human approval — `Status: Approved` requires the explicit approval question above.

### Planning Next Instructions (when Engineering-ready and Approved)

When the specification reaches `Readiness: Engineering-ready` and is `Status: Approved`, the final response MUST provide next instructions to create the implementation plan:

1. **Context Compaction Recommendation:** Recommend performing a context compaction (e.g., running `/compact` or compacting context) before creating the plan to ensure planning begins in a fresh, token-efficient context.
2. **Copy-Pasteable Planning Command:** Provide the exact command to invoke `/detailed-plan` in a standalone code block with the relative specification path:

```
/detailed-plan [REL_PATH_TO_SPEC] [OPTIONAL_ADDITIONAL_INSTRUCTIONS]
```
*(substitute `[REL_PATH_TO_SPEC]` with the real relative path to the approved specification file, e.g., `/detailed-plan docs/specs/<spec-filename>.md`)*.

Do not create or offer an implementation task plan and do not begin coding.

#### `--to-plan`: chain instead of handing off

This is the whole behavioral difference the flag makes. Everything above this heading still runs unchanged, the approval question included.

When `--to-plan` was supplied **and** the specification is `Readiness: Engineering-ready` **and** `Status: Approved`:

1. Give the completion report above, minus the compaction recommendation and the copy-pasteable command — neither applies when nobody has to type anything.
2. State in one line that planning is continuing in this session and that its context carries the specification conversation with it.
3. Read `.agents/skills/detailed-plan/SKILL.md` and execute it against the specification path just written, which is a linked approved spec and therefore enters the Spec-Hydrated Fast Path.
4. Hand off from there exactly as `detailed-plan` §9 already prescribes, compaction recommendation and `/parallel-subagent-driven-development` command included.

When `--to-plan` was supplied and the specification did **not** reach both `Engineering-ready` and `Approved`, produce no plan: report the completion states as normal, say in one line that the chain did not run and which of the two conditions is missing, and stop. An unapproved specification is the one thing the flag may never route around.

`--to-plan` changes who types the next command and nothing else. It never merges the two documents, never lets planning edit the specification, and never lets a planning finding silently widen specification scope — that escalation path stays exactly as `detailed-plan` §8 defines it.
