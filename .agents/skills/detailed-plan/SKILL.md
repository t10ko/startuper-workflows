---
name: detailed-plan
description: Profile-routed TDD planning workflow with evidence-gated discovery, failure-class coverage for bugs, minimal meaningful tests, and explicit integration gates.
---

# Detailed Plan Workflow Skill

Profile-routed TDD planning workflow that creates a decision-complete `implementation_plan.md` for executable development.

## Purpose

Plan features, refactors, and bug fixes thoroughly without guessing or writing speculative code.
This workflow plans only—it does not edit production code or tests directly.

It MUST:
1. Explain the problem and root cause before proposing edits.
2. Identify the source owner and fix contract at the producer level (no defensive shims).
3. Classify task type automatically (`BUG` vs `NON-BUG`) and prove failure-class coverage for bugs — verifying the linked spec's sibling list, or sweeping for it when no spec is linked.
4. Run evidence-gated read-only discovery, dispatching subagents ONLY for surfaces with preflight uncertainty.
5. Produce the smallest sufficient TDD verification portfolio using strict admission gates.
6. Enforce mandatory integration decisions and end with a fresh run of the project's verify command.

---

## Repository Invariants

- Run all Python commands with `python3`, never a bare `python`.
- End every executable handoff with a fresh run of the project's verify command (`[project] verify_cmd` in `.agents/config.toml`).
- Use `rg` for search queries.
- Fix source contracts at the owner; do not plan defensive shims or compatibility bridges.
- For product-facing work, if `docs/USER_PERSONAS.md` exists, read it first; otherwise proceed without it.
- Preserve NOTHING AT ONCE: no single task sweeps an entire feature area in one operation; each unit of work stays independently landable.
- Tests must never make real network/provider API calls.

---

## 1. Route Profile & Classify Task

Use the smallest valid profile:

| Profile | Entry Rule | Analysis Strategy |
| --- | --- | --- |
| `COMPACT` | Single local behavior, obvious owner, no API/DB/IPC/concurrency boundary | Lead direct evidence pass (0 subagents) |
| `STANDARD` | Feature, bug, cleanup, or multi-file refactor with known ownership | Evidence-gated discovery (0-4 subagents based on preflight gaps) + conditional review |
| `ARCHITECTURE` | Shared contract, persistence, permissions, migration, or orchestration | `STANDARD` panel + `architect.md`; specialists when triggered |
| `INVESTIGATION` | Cause or owner confidence is `MEDIUM`, `LOW`, or `UNCERTAIN` | Read-only evidence probes; no production-edit plan |
| `WORKFLOW_DOCS` | Prompt/workflow/agent/docs-only behavior | Two parallel scenario critics for non-trivial changes |

### Routing & Classification Rules
- **Task Classification:** Automatically tag task as `BUG` (bug, error, regression) or `NON-BUG` (feature, refactor, docs).
- **Failure-Class Source:** A `BUG` task with a linked task spec sets `Failure-class source: SPEC` — the spec's §5b failure-class section owns the sibling list, and this workflow verifies coverage rather than re-running discovery. A `BUG` task with no linked task spec sets `Failure-class source: PLAN SWEEP` and runs the sweep itself (§8). `NON-BUG` tasks set `N/A`.
- Unknown root cause or owner routes to `INVESTIGATION`.
- Shared contract or persistence changes route to `ARCHITECTURE` via [.agents/workflows/architect.md](../../workflows/architect.md).

---

## 2. Evidence Preflight

Before planning or dispatching helpers:
- Inspect relevant code, tests, rules, prompts, diffs, and history. Avoid bulk-reading.
- **Spec Staleness Check:** When a task spec is linked, run:
  ```bash
  python3 .agents/scripts/spec_staleness.py docs/specs/<the-linked-spec>.md
  ```
  Exit `0` (clean) -> Wave 1 scouts skip un-changed cited files; Exit `1` -> full surface audit.
- **Grounding Artifact:** When `docs/specs/grounding/<spec-slug>.md` exists, Wave 1 scouts read it first to prevent duplicate file read volume across agents.
- **Plan History Search:** Run `python3 .agents/scripts/detailed_plan_history.py search --limit 5 <terms>` for prior lessons.
- Trace entry point, owner, producers, consumers, and persistence using `rg`.
- Locate test harness (fixtures, factories, test DB) before proposing tests.
- Record root cause confidence (`ABSOLUTE`, `HIGH`, `MEDIUM`, `LOW`). Below `HIGH` routes to `INVESTIGATION`.

**Grounding freshness** — before reading any grounding artifact body, follow `.agents/references/grounding-freshness.md`, the single owner of the staleness-check protocol and of what each exit code obliges you to do.

---

## 3. Evidence-Gated Subagent Discovery

Refer to [.agents/skills/detailed-plan/references/subagents.md](references/subagents.md) for full subagent contracts and return schemas. Dispatch Wave 1 scout briefs via the registered `plan-scout` specialist (or built-in read-only `Explore` agent).

**The role names below are not registered agent types — never pass one as `subagent_type`.** Each is a prompt brief you give to the registered `plan-scout` specialist or the built-in read-only `Explore` agent. Their absence from the agent registry is the design, not a gap, and reporting one as missing is a false alarm.

**Concurrency: at most N concurrent agents** (`.agents/AGENTS.md`, Agent Orchestration; N from `.agents/config.toml`, `[worktrees] max_concurrent`). Wave 1 can trigger six scouts; when it does, dispatch in batches of ≤ N — a queued batch starts as soon as a slot frees (one completion or one merge), never only after the whole running batch drains. Wave 2's critics count against the same cap.

### Dispatch Rules
- **Spec-Hydrated Fast Path:** When a valid approved task spec is linked (and passes spec staleness check), bypass Wave 1 discovery scouts entirely. Hydrate the TDD Matrix and Execution Queue directly from the spec's §5b failure-class sibling list, §6 contracts, and §11 execution queue.
- **No Mandatory Quotas:** Subagents are dispatched ONLY when preflight evidence leaves unresolved gaps.
- **`FailureClassAnalyst`:** Dispatched ONLY for `BUG` tasks with no linked task spec. When a spec is linked it already carries the sibling list, and re-running discovery here would re-open a scope decision the user already made.
- **`ProblemFixAnalyst`:** Dispatched ONLY if preflight root-cause confidence is `< HIGH`.
- **`IntegrationBoundaryScout`:** Dispatched ONLY if service, DB, process, or IPC boundaries are crossed.
- **`ExistingCoverageScout`:** Dispatched ONLY if existing test coverage is non-obvious.
- **`BehaviorScenarioScout`:** Dispatched ONLY if scenario space is complex or unmapped by spec.
- Record any skipped subagent as `not dispatched — lead preflight complete` (or `not dispatched — spec-hydrated fast path`).

---

## 4. Lead Synthesis & Problem Model

The lead—not a subagent—reconciles evidence and establishes:
- `Observed`, `Expected`, and `Actual` behavior for bugs.
- Root cause, confidence, broken contract, and smallest source-level fix mechanism.
- Architecture Decision: `LOCAL_FIX_OK` | `SYSTEM_CHANGE_REQUIRED` | `INVESTIGATE_FIRST`.
- De-duplicated candidate scenario ledger (`KEEP`, `MERGE`, `DROP`, `NEEDS_EVIDENCE`).

---

## 5. Test Admission Gate

A test enters the plan ONLY when all 8 checks pass:
1. **Evidence:** Derived from requirement, bug, contract, or permission rule.
2. **Unique value:** Detects a distinct regression not already proven.
3. **Observable assertion:** Checks returned behavior, state, or emitted contract (not mock calls).
4. **Correct level:** Lowest level proving the contract while retaining real boundaries.
5. **Meaningful red:** Fails for the intended behavioral reason before fix.
6. **Realism:** Resembles production contract composition.
7. **Non-duplication:** Not a rephrasing of another test.
8. **Maintenance value:** Protected risk justifies future maintenance.

Reject or merge candidates failing any check. Parameterize data variants.

---

## 6. Mandatory Integration-Test Decision

Every plan must state: `Integration test decision: REQUIRED | NOT REQUIRED`.
- `REQUIRED` if persistence, transactions, API boundaries, async events, process boundaries, or permissions cross components.
- `NOT REQUIRED` valid ONLY if no boundary changes and an existing integration test proves the exact changed contract.

---

## 7. Wave 2 Conditional Review

Refer to [.agents/skills/detailed-plan/references/subagents.md](references/subagents.md).
- Run `TestMinimalityCritic` and `IntegrationAdequacyCritic` via the registered `dimension-reviewer` specialist (or built-in read-only `Explore` agent) ONLY when candidate shortlist >6 tests or test boundaries/levels are disputed.
- For shortlists of 1–6 tests, the lead applies the Test Admission Gate directly.

---

## 8. Failure-Class Coverage Protocol

Mandatory for all `BUG` tasks. Which path runs is decided by `Failure-class source` (§1).

### Spec-linked path — verify, do not rediscover

Discovery already happened in the spec's §5b, where each sibling was an explicit user scope decision. This workflow proves the plan covers it:

1. **Coverage check:** Every sibling the spec put in scope has an `Execution Queue` entry and a `TDD Matrix` row.
2. **Mechanism check:** A spec recording `SHARED_OWNER_CANDIDATE` must not be planned as N local repairs. That contradiction is a blocker, not a planning choice.
3. **Escalation, not absorption:** A sibling found during preflight that the spec does not list goes back to the spec as a new question — never a silent addition to plan scope. Record it under `New siblings found during preflight` and stop for the decision.

### Spec-less path — run the sweep

Reachable only when no task spec is linked, which is real: not every plan is preceded by a spec. This path is the exception, and the plan must record which path it took.

1. **Abstract Pattern Extraction:** Extract the underlying contract error or anti-pattern at the concept level, not the reported example's literal shape.
2. **Semantic Subagent Probe:** `FailureClassAnalyst` executes semantic code audits + `rg` queries across producers, consumers, handlers, and prompts (refer to [.agents/skills/detailed-plan/references/subagents.md](references/subagents.md)).
3. **Comprehensive Scope Inclusion:** Include ALL confirmed sibling instances in the plan's `Execution Queue` to resolve the issue class in one diff.
4. **Widened scope is a human decision:** When the sweep expands scope past the original request, surface that expansion for approval before the plan is finalized using `AskUserQuestion`. Frame the question via a single Unified Plain-Language Context Block (2-3 sentences: what this is, why it matters, current situation) and symmetric outcome options (`[Action] — [Tradeoff]`), strictly omitting internal tracking IDs.

---

## 9. Required Output Schema & Handoff

**A document body over 8,000 characters is written by a dispatched `document-writer`** (`.agents/specialists/document-writer.md`), which returns only the path it wrote and that file's byte size; the orchestrator then reads back only the sections it must act on. The threshold is exclusive: a body of exactly 8,000 characters is written by the orchestrator itself, and only a body above that reaches the writer. It decides who writes the document, never how long the document may be, and no real finding is ever trimmed, thinned, or dropped to land on either side of it.

Output plan must strictly follow [.agents/skills/detailed-plan/references/output_template.md](references/output_template.md).

For Execution Queue grouping, thinking tier assignment, and execution handoff, follow [.agents/skills/detailed-plan/references/execution_grouping.md](references/execution_grouping.md).
Execution enters `parallel-subagent-driven-development` ([.agents/skills/parallel-subagent-driven-development/SKILL.md](../parallel-subagent-driven-development/SKILL.md)).

### Implementation Next Instructions (when Plan is Ready)

When the plan is finalized and ready to be implemented, the final response MUST provide next instructions to start execution:
1. **Context Compaction Recommendation:** Recommend performing a context compaction (e.g., running `/compact` or compacting context) before starting execution to ensure the orchestrator begins in a fresh, token-efficient context.
2. **Copy-Pasteable Execution Command:** Provide the exact command to invoke `/parallel-subagent-driven-development` in a standalone code block with the relative plan path — **always including all three execution-mode flags**, so the executing session starts implementation without re-asking the autonomy mode:

```
/parallel-subagent-driven-development [REL_PATH_TO_PLAN] --dont-stop --dont-ask --dont-defer [OPTIONAL_ADDITIONAL_INSTRUCTIONS]
```
*(substitute `[REL_PATH_TO_PLAN]` with the real relative path to the implementation plan, e.g., `/parallel-subagent-driven-development docs/plans/<plan-filename>.md --dont-stop --dont-ask --dont-defer`; strip a flag only when the user explicitly wants that axis's default behavior — `--dont-stop` runs without pauses or check-ins, `--dont-ask` decides every question by best judgment and documents each decision, `--dont-defer` fixes every finding surfaced during the run and reports all of them in the final message)*.

---

## 10. Final Self-Review Checklist

Verify before finalizing:
- Smallest valid profile selected.
- Problem / Change Model clearly explains root cause and source fix.
- Subagent dispatches were evidence-gated (or recorded as `not dispatched — lead preflight complete`).
- Failure-class coverage proven for bugs: the linked spec's sibling list verified against the Execution Queue, or — with no linked task spec — swept via `FailureClassAnalyst`. Marked `N/A` for non-bugs. No sibling added to scope without the spec or the human saying so.
- TDD rows passed Test Admission Gate; integration decision explicitly justified.
- Execution Queue labeled with parallel safety and thinking tiers, and naming no model anywhere — `.agents/rules/model-assignment.md` is the single owner of every model choice.
- Critical path identified and minimized; blocking groups de-bloated of non-blocking tasks; shared settings/base schemas isolated to Wave 0 bootstrap. Concurrency respects the configured cap N (`.agents/config.toml`, `[worktrees] max_concurrent`).
- Execution Queue carries per-task `## Task <N>` headings, each with `Requirements`, `Group`, `Files`, `Consumes`, and `Produces`. A queue that stops at the group level fails this gate: it leaves the execution workflow no unit to dispatch, so it dispatches the whole group to one agent.
- `python3 .agents/scripts/plan_merge_candidates.py <plan path>` exits 0, or every file it names is resolved in the plan — given one owning task the others depend on, fused into one task under [sizing-agent-work.md](../../rules/sizing-agent-work.md) §3.2's one condition, or kept split with a one-sentence reason beside its group ([execution_grouping.md](references/execution_grouping.md) §1.0). A file declared by two groups makes one wait for the other to merge, costing a whole group cycle. **Single ownership is the first answer and fusing is the last**, because fusing many tasks that share a hot file is how a plan grows a task nobody can review. Task size itself is owned by [sizing-agent-work.md](../../rules/sizing-agent-work.md) §3, including the finish line (§3.4) every `## Task <N>` must carry.
- Ends with a fresh run of the project's verify command and a conventional commit.
- Final instructions include context compaction recommendation and copy-pasteable `/parallel-subagent-driven-development [REL_PATH_TO_PLAN] --dont-stop --dont-ask --dont-defer [OPTIONAL_ADDITIONAL_INSTRUCTIONS]` code block, with all three execution-mode flags present so execution starts without re-asking the autonomy mode.
