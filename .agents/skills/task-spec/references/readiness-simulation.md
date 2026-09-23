# Implementation-readiness simulation

This reference belongs to step 10 of the task-spec workflow — read it when behavioral requirements are stable and you are running the implementation-readiness simulation.

## 10. Implementation-readiness simulation

This is the main defense against discovering important questions only after coding begins.

After behavioral requirements are stable, run `task-spec-adversarial-critic` (in readiness mode). For broad tasks, run separate readiness lenses concurrently:

- backend/data implementer;
- client/UI or API consumer;
- tester/security/operations reviewer.

Ask each reviewer:

> Assume you must implement and verify this task without inventing product behavior or high-cost design. What questions are still unanswered?

Require every returned question to be classified as:

- `Requirement gap` — Level 1;
- `Contract/data gap` — Level 2;
- `Material design gap` — Level 3;
- `Implementation discretion` — Level 4;
- `Not a real gap` — already answered or irrelevant.

For each claimed gap, require:

- exact affected section or missing section;
- why the answer matters;
- consequence of guessing;
- recommended default when supportable.

The coordinator must independently verify every finding. Do not blindly turn reviewer questions into user questions.

### Readiness policy

- Any unresolved Requirement gap blocks `Requirements ready`.
- Any unresolved Contract/data gap blocks `Requirements ready`.
- Any unresolved authorization blocker blocks `Requirements ready`.
- In adaptive or `--design` mode, any unresolved high-impact Material design gap blocks `Engineering-ready`.
- In `--requirements-only` mode, material design gaps do not block `Requirements ready`, but must be listed clearly under Open engineering decisions.
- Implementation discretion never blocks readiness.

After corrections, run one final readiness pass only if the corrections were material.

