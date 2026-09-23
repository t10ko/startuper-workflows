# Task-spec document template

This is the canonical 23-section structure instantiated for every specification.

```markdown
# Task Specification: <title>

**Status:** Draft
**Readiness:** Requirements incomplete | Requirements ready | Engineering-ready
**Mode:** Requirements-only | Adaptive | Design
**Source:** <ticket, issue, request, or conversation>
**Created:** YYYY-MM-DD
**Updated:** YYYY-MM-DD

## 1. Problem and intended outcome

### Problem
...

### Intended outcome
...

## 2. Scope

### In scope
- ...

### Out of scope
- ...

### Must remain unchanged
- ...

## 3. Current behavior and repository constraints
...

## 4. Actors and authorization

### Actors and identities
- ...

### Authorization invariants
- ...

### Permission matrix
| Operation | Actor / identity | Resource scope | Ownership / tenant condition | Required state | Allow or deny | Observable denial behavior |
|---|---|---|---|---|---|---|

### Sensitive-field visibility
| Field or data class | Who may view | Who may modify | Redaction or disclosure rule |
|---|---|---|---|

## 5. Behavioral requirements
- **REQ-001:** The system MUST ...

## 6. Flows

### F-01 — Primary flow: <name>
- **Actor / trigger:** ...
- **Preconditions:** ...
- **Steps:** ...
- **Outcome:** ...
- **Related requirements:** ...

### Alternate flows
...

### Error and recovery flows
...

## 7. States, transitions, and invariants
| From state | Trigger | Guard / permission | To state | Side effects | Invalid-transition behavior |
|---|---|---|---|---|---|

## 8. Data and persistence contract

### Conceptual entities and relationships
- ...

### Identity, ownership, and cardinality
- ...

### Persistence and source of truth
- ...

### Mutability, history, and audit semantics
- ...

### Lifecycle, retention, deletion, and restoration
- ...

### Consistency and atomicity requirements
- ...

### Required access patterns and scale assumptions
- ...

### Sensitive data classification
- ...

## 9. Inputs, outputs, validation, and error contract
<Include the substance and intent of user-facing error and empty-state messages when it affects understanding — what the user must learn from the message and what action it should prompt. Exact wording/copy remains Level 4 implementation discretion.>

## 10. External contracts and dependencies

### API, event, CLI, or UI contract
...

### Dependency failure behavior
<Per dependency: timeout, retry count and backoff strategy, circuit-breaker or fallback behavior, and any cost or rate-limit budget that bounds how much the integration may spend or call before degrading.>

### Configuration and secrets contract
<Which behavior is externally configurable, the source of truth for each configuration value and secret, and required behavior when a needed configuration value or secret is missing or invalid.>

## 11. Concurrency, idempotency, and partial failure
| Scenario | Required outcome | State afterward | Retry / recovery | User or operator visibility |
|---|---|---|---|---|

## 12. Edge cases and boundary conditions
- **EC-001:** Condition → required outcome.

## 13. Quality attributes
<Only relevant measurable security, privacy, accessibility, localization, performance, reliability, capacity, cost, observability, third-party content rights/licensing, and compatibility requirements.>

### Accessibility requirements
<When the task has a UI or user-facing surface: keyboard operability, focus management, screen-reader labeling, and color-contrast/motion requirements. Treat these as Blocker-level, not Polish.>

## 14. Migration, rollout, and compatibility constraints
<State first whether the project's own contract-compatibility conventions call for a migration/rollout section at all before populating one. When relevant: behavior for existing data/users/clients, backfill semantics, mixed-version states, rollout constraints, rollback expectations, and feature-flag behavior. Include an explicit kill-switch question: how the feature is disabled if it is functioning but misbehaving on cost, rate limits, or resource consumption. Do not create implementation tasks.>

## 15. Engineering design decisions
<Include in adaptive or design mode only when decisions are material.>

### DD-001 — <decision>
- **Status:** Open | Tentative | Accepted | Parked | Implementation discretion
- **Context and constraints:** ...
- **Chosen design:** ...
- **Alternatives considered:** ...
- **Rationale:** ...
- **Consequences and risks:** ...
- **Affected requirements / flows:** ...
- **Generalization basis:** ...
- **Empirical evidence:** ... <when this decision was settled or informed by a `technical-spike`: the brief path `verify/<slug>_brief.md`, the winning script path, the measurement date, and the model-chain — a durable citation, never restated numbers, so a stale or never-adopted spike-backed decision stays searchable>
- **Related workflows:** ... <name any project-specific specialist review process this decision still requires, if the project defines one>

### Data storage design
<When material: logical records/fields, keys, relationships, constraints, indexing needs, transaction boundaries, and migration approach. Do not write DDL.>

### Contract or integration design
<When material: interface shape, ordering, versioning, delivery semantics, timeout/retry boundary, and compatibility.>

### LLM call-site design
<When material: for a new or materially changed LLM call site the feature ships, cover which model that call site uses, temperature or equivalent sampling setting, structured-output validation approach, and any project-documented prompt-authoring constraints. This describes the shipped feature's own runtime call site, never the model assigned to any agent, which `.agents/rules/model-assignment.md` alone owns.>

## 16. Acceptance criteria
<State each criterion's verification method (unit test, integration test, or manual/exploratory check) and, when it differs from the requirement's own boundary, which downstream consumer verifies against it next.>
- **AC-001:** Given ..., when ..., then ...

## 17. Traceability
| Requirement | Flows | Authorization rule | Data rule / contract | Acceptance criteria | Verification method | Boundary |
|---|---|---|---|---|---|---|

## 18. Assumptions
- **A-001:** ...

## 19. Open questions
- **Q-001 — Level 1|2|3:** ...

## 20. Decision log

### D-001 — <decision title>
- **Status:** Open | Tentative | Accepted | Parked
- **Class:** Requirement | Contract | Engineering design
- **Decision:** ...
- **Rationale:** ...
- **Rejected alternatives:** ...
- **Consequences:** ...
- **Affected sections / IDs:** ...

## 21. Implementation discretion
<List deliberate Level 4 choices that are safe to leave open. This is not a task plan.>

## 22. Implementation execution guidance
<Advisory only, for whoever plans or executes next. Never file paths, function names, or a task list.>

### Parallel execution groups
| Group | Requirement / flow / data IDs | Independent or sequential | Coupling reason |
|---|---|---|---|

### Complexity signals per group
| Group | Complexity signals (risk, readiness-critic, design) |
|---|---|

<Signals only — never a model, and never a thinking tier. `.agents/rules/model-assignment.md` is the single owner of every model choice for an agent, and `.agents/skills/detailed-plan/references/execution_grouping.md` §2 owns thinking tiers and reads this column to decide them. Either value written here would be a second writable store (`.agents/rules/single-source-of-truth.md`). This is separate from the model the shipped feature's own LLM call site uses — see LLM call-site design.>

## 23. Readiness assessment
- Requirements blockers: ...
- Contract blockers: ...
- Engineering-design blockers: ...
- Residual risks: ...
- Audit status: ...
```
