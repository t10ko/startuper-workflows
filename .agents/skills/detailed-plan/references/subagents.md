# Wave 1 and Wave 2 Subagent Specifications

This document defines the prompt contracts, return schemas, and dispatch rules for read-only subagents dispatched during the `detailed-plan` workflow.

## Subagent Dispatch Invariants

1. **Read-Only Exploration:** Wave 1 scouts run via the registered specialist `plan-scout` (`.agents/specialists/plan-scout.md`) or built-in read-only `Explore` agent. Wave 2 critics run via the registered specialist `dimension-reviewer` (`.agents/specialists/dimension-reviewer.md`) or built-in read-only `Explore` agent. **The role names in this document are not registered agent types — never pass one as `subagent_type`.** `ProblemFixAnalyst`, `FailureClassAnalyst`, and every other name below is a prompt brief, not an agent to look up. Their absence from the agent registry is the design; do not report it as a missing specialist. This is the opposite of `task-spec` and `technical-spike`, whose named specialists *are* registered agent types — do not carry their registration-gap wording over to this workflow.
2. **Concurrency Cap:** **Max N concurrent agents** per `.agents/AGENTS.md`'s Agent Orchestration section — N from `.agents/config.toml` (`[worktrees] max_concurrent`). Six Wave 1 scouts can trigger at once; dispatch in batches of ≤ N — a queued batch starts as soon as a slot frees (one completion or one merge), never only after the whole running batch drains.
3. **Model:** State no model here and pass no `model` argument. Wave 1 scouts and Wave 2 critics are investigation roles, and `.agents/rules/model-assignment.md` is the single owner of which model they get — read it from there rather than from a copy kept here.
4. **Dispatch Prompt Requirements:** Every prompt MUST include role, task, exact scope, relevant files, repository invariants, read-only permission, required output schema, and:
   - `Do not edit files.`
   - `Do not propose work outside the assigned scope.`
   - `Do not invent unrelated edge cases.`
   - `Do not turn every finding into a test.`
   - `If you stop before covering everything in your assigned scope, name the exact surface you did not reach in a "Not covered" section.`

---

## Wave 1 Scout Specifications

### Spec-Hydrated Fast Path
When an approved task spec is linked and passes staleness validation, Wave 1 scouts are bypassed. The lead hydrates the TDD Matrix, architecture contracts, and execution queue directly from the spec (§5b, §6, §11).

### `ProblemFixAnalyst`
Dispatched when root cause or fix mechanism confidence is below `HIGH`.

**Return Schema:**
- `Requested/expected behavior`
- `Actual behavior or current limitation`
- `User/system impact`
- `Reproduction or source evidence`
- `Root cause and confidence for bugs` (`ABSOLUTE`, `HIGH`, `MEDIUM`, `LOW`)
- `Source owner and broken/missing contract`
- `Smallest source-level fix mechanism`
- `Why the fix prevents recurrence`
- `Rejected shim, local workaround, or over-broad fix`
- `Non-goals and open uncertainties`

### `FailureClassAnalyst` (Spec-less `BUG` tasks only)
Dispatched ONLY for `BUG` tasks with no linked task spec, to conduct semantic and structural codebase exploration for sibling failure instances.

When a task spec is linked, its §5b failure-class section already carries the sibling list as decided user scope, and this role is not dispatched — the plan verifies that list instead. The canonical contract for that discovery lives in [.agents/skills/task-spec/agents/discovery-scout.md](../../task-spec/agents/discovery-scout.md); keep this schema aligned with it rather than letting the two drift.

**Return Schema:**
- `Abstract failure pattern and broken contract definition`
- `Structural search queries used` (`rg` queries, regex patterns)
- `Candidate files and components audited` (producers, consumers, handlers, models, prompts)
- `Confirmed sibling instances to include in plan scope`
- `Non-matches / out of scope with evidence-backed rationale`
- `Comprehensive sweep status` (`COMPREHENSIVE (N instances found)` vs `CLEAN`)

### `BehaviorScenarioScout`
Dispatched when scenario space is complex, multi-flow, or unmapped by an existing spec.

**Return Schema:**
- `Stable scenario ID`
- `Actor and permission requirement`
- `Starting state, action, and observable outcome`
- `Classification` (Primary, alternate, validation, permission, failure, recovery, concurrency, compatibility)
- `Evidence source`
- `Exact risk or regression represented`
- `Existing scenario/test that may already cover it`
- `Verdict` (`KEEP`, `MERGE`, `DROP`, `NEEDS_EVIDENCE`)

### `IntegrationBoundaryScout`
Dispatched when service, DB, process, filesystem, or IPC boundaries are touched.

**Return Schema:**
- `Components crossed by the behavior`
- `API, persistence, transaction, migration, UI/IPC bridge, async/event, serialization boundaries`
- `Existing integration harnesses and representative test paths`
- `Changed versus unchanged boundaries`
- `Smallest integration scenario needed for each changed boundary`
- `Exact likely test path and command`
- `Components to keep real vs outer systems to fake`
- `Integration test required: YES | NO` (with evidence)

### `ExistingCoverageScout`
Dispatched when existing test coverage or harness conventions are non-obvious.

**Return Schema:**
- `Existing tests covering the owner contract or neighboring behavior`
- `Tests to extend instead of creating new files`
- `Genuine coverage gaps introduced by this task`
- `Fixture/factory/harness conventions to reuse`
- `Tests whose expected contract must change`
- `Anti-patterns to avoid` (duplicate, brittle, tautological, over-mocked)

### `PermissionBoundaryScout` (Conditional)
Dispatched whenever roles, ownership, tenant isolation, authentication, or authorization are touched.

**Return Schema:**
- `Actor x operation x resource permission matrix`
- `Enforcement point for each operation`
- `Allowed and forbidden outcomes`
- `Information-disclosure/enumeration risks`
- `Required no-state-mutation assertion for denied operations`
- `Existing permission tests and missing public-boundary proof`

---

## Wave 2 Critic Specifications

Wave 2 critics run concurrently *only* when the candidate shortlist has >6 tests or when test boundaries/levels are disputed.

### `TestMinimalityCritic`
For each shortlisted scenario, evaluates minimality and assertion quality.

**Return Schema:**
- `Verdict` (`KEEP`, `MERGE`, `DROP`, `NEEDS_EVIDENCE`)
- `Unique regression protected`
- `Redundancy with existing/selected tests`
- `Correct test level` (Unit, Contract, Integration, E2E)
- `Assertion quality check`
- `Recommendation` (parameterize, extend existing test, or create new)
- `Specific reason for dropping low-value tests`

### `IntegrationAdequacyCritic`
Evaluates the integration test decision and boundary correctness.

**Return Schema:**
- `Integration decision validity` (`REQUIRED` vs `NOT REQUIRED`)
- `Real boundary exercised by each integration candidate`
- `Components incorrectly mocked or bypassed`
- `Missing DB/API/permission/async/bridge proof`
- `Existing harness to reuse`
- `Validity of any waiver evidence`
