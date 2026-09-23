# Requirements and design quality audit

This reference belongs to step 9 of the task-spec workflow — read it when auditing requirements and design quality, unless `--lean` was supplied.

## 9. Requirements and design quality audit

Treat the document as code written in natural language.

### Behavioral audit checkpoint

Unless `--lean`, or very small and `--parallel` was not supplied, run concurrently:

**This checkpoint re-fires only on a decision that changed a section a specialist below owns, and it dispatches only that specialist plus `task-spec-adversarial-critic`.** It does not re-fire on an accumulated decision count, and it never dispatches the whole list to see which one has something to say — an accepted decision that touched no specialist's own sections is a decision this checkpoint has nothing to audit. Name the changed section and the specialist that owns it when the checkpoint fires; if no specialist owns the changed section, `task-spec-adversarial-critic` alone runs.

- `task-spec-adversarial-critic`;
- `task-spec-contract-analyst` when a decision accepted since the last audit changed an actor, state, transition, failure/recovery path, permissions, persistence, UI/frontend surface, or LLM call site;
- `task-spec-risk-analyst` when one changed a dependency, failure mode, concurrency surface, cost/rate-limit budget, or compatibility promise.

Every specialist in this list is auditing the drafted specification, not rediscovering the repository. Give each one the specification path plus the explicit section list it must read: the shared spine (§1 Problem and intended outcome, §2 Scope, §5 Behavioral requirements, §16 Acceptance criteria, §17 Traceability, §19 Open questions) plus its own lens sections — `task-spec-contract-analyst` reads §4, §5a, §6, §7, §8, the accessibility subsection of §13, and the data-storage/LLM subsections of §15; `task-spec-risk-analyst` reads §10, §11, §13, and §14. `task-spec-adversarial-critic` alone reads the whole document — cross-section consistency is its assignment. Each specialist locates its sections with `rg -n '^#{2,3} '` against the specification path. Also give each one any `Confirmed` discovery findings for that lens still available in this conversation. Require it to reconcile its assigned sections against that record before reading anything else. Read source to verify a claim the document makes, to settle a contradiction against a recorded finding, or to cover a surface that entered scope after discovery — not to rebuild a model that already exists.

When this checkpoint fired because scope changed rather than because five decisions accumulated, the newly in-scope surface was never scouted. Treat it as undiscovered and read it from source.

Require findings to name affected IDs or sections, explain consequences, and classify each as `Blocker`, `Important`, or `Polish`.

The coordinator must:

1. deduplicate findings;
2. reject unsupported speculation;
3. fix evidence-backed non-decision issues;
4. classify unresolved questions by level;
5. ask one question at a time.

Check:

- completeness;
- clarity and canonical terminology;
- consistency across requirements, matrices, flows, design decisions, and acceptance criteria;
- testability and measurability;
- authorization completeness;
- data-semantic completeness;
- failure, partial-failure, and concurrency coverage;
- compatibility and migration coverage;
- traceability;
- literal-compliance loopholes;
- inappropriate implementation contamination.

Run up to three coordinator revision passes.

