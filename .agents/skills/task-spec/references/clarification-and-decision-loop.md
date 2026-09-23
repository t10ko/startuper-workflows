# Clarification and decision loop

This reference belongs to step 8 of the task-spec workflow — read it when taking the highest-ranked unresolved item into clarification or decision-workshop mode.

Take the highest-ranked unresolved item.

- Level 1 or 2 with a factual/behavioral gap → clarification mode.
- Level 1, 2, or material Level 3 with credible alternatives → decision-workshop mode.
- Level 3 in `--requirements-only` mode → record under Open engineering decisions, unless it exposes an unresolved Level 1 or 2 issue.
- Level 4 → record as Implementation discretion only when useful; otherwise omit it.

For a Level-3 decision where fewer than two distinct approaches are already on the table, first run `task-spec-risk-analyst` (for candidate approach generation) to generate 2–4 genuinely distinct candidates; feed its output into the decision evaluation and into the decision's `Alternatives considered` entry in the specification's decision log.

For consequential choices, optionally run `task-spec-risk-analyst` concurrently from up to three lenses:

- user and business outcome;
- correctness, security, privacy, and abuse resistance;
- compatibility, reversibility, data integrity, operations, and long-term complexity.

**Empirical hand-off (never auto-dispatch).** When a Level-3 decision cannot be settled by analysis because it depends on unknown runtime behavior — accuracy, feasibility, or performance over real data (the "fixed rule versus judgment-based mechanism" example is the archetype) — pause that one decision and surface `technical-spike` to the user as an option inside the normal `AskUserQuestion` decision flow. Never run code and never auto-dispatch a spike: task-spec is forbidden from running code, and technical-spike never auto-invokes. If the user declines the spike, the decision **defaults to Parked** as an Open engineering decision with the empirical question recorded verbatim (this does not block `Requirements ready`, but blocks `Engineering-ready` unless deferred with a safe boundary); accept-on-judgment, flagged "unverified — not empirically validated," only when the user explicitly vouches for a design. Never silently guess a runtime fact. Only the analytically-unresolved surviving candidates are carried into the spike, to avoid spending live-call budget on already-eliminated approaches.

A returned spike brief updates the decision through this verdict → state crosswalk (the brief is the source of truth for what was measured; the specification's decision log is the source of truth for what was decided; a passing brief is never itself an accepted decision):

| Spike verdict | Decision status | Next |
|---|---|---|
| Clean winner | Accepted | cite the winning script's numbers via the Empirical-evidence line; the baseline's agreement interval is the regression reference |
| No winner | Open (if re-scoping) or Parked (if awaiting a boundary) | record the real gap; re-scope or escalate; never force Accepted |
| Ambiguous / split | Tentative → Accepted after the user picks the axis | re-enter decision-workshop; the trade-off is one `AskUserQuestion` |
| Indistinguishable | resolved by a non-empirical criterion, or Implementation discretion | revert to cost/simplicity; never force a winner |

After every accepted answer:

1. Update the specification immediately.
2. Update the decision log and status.
3. Update permission/data matrices and design decisions where affected.
4. Replace invalidated wording.
5. Update flows, state rules, requirements, edge cases, and acceptance criteria.
6. Recheck traceability.
7. Re-run only relevant parts of the coverage scan.

Do not impose a rigid total question limit. After five accepted decisions, run an audit. Stop when only Level 4 choices or safe, explicitly documented assumptions remain.

When the user shows fatigue signals — repeated terse, uncertain, or deflecting answers — offer a three-way choice instead of continuing to ask one at a time indefinitely or ending the session outright: continue one question at a time, batch the remaining open items as documented Assumptions, or stop and save the current state.

If the user says `finish spec`, `done`, or `stop`, save the current state, run the final audit, and leave unresolved items explicit rather than guessing.
