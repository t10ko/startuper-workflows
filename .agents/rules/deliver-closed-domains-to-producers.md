---
trigger: glob
globs: "agentic_workflows/**"
paths:
  - "agentic_workflows/**"
---

# Deliver a Closed Domain to Whoever Must Produce It

Recorded 2026-08-15 at the user's direction, after a sweep of ~120
closed-domain fields across ~245 model-facing surfaces found ten enforced
against a model that was never shown the legal values.

## The rule

**If a field's legal values form a closed set, the producing model must be
given that set.** Enforcement without delivery is a defect the moment it is
written — not once a model guesses wrong. A model asked for a value from a
vocabulary it cannot see has one option: invent one.

## Choosing the delivery route

The route is decided by the set's lifetime, not by preference. Five routes;
every closed-set field takes exactly one, and whichever runs, delivered set
and legal set derive from one owner:

- **`static-schema-enum`** — fixed at class-definition time: type the field
  `Literal[...]` or a `StrEnum`. `to_llm_schema` emits `enum`, the
  prompt-building stage renders that schema into the prompt, and Pydantic's own
  rejection message names
  every permitted value inside the existing retry. One edit buys delivery,
  validation, and feedback.
- **`runtime-list-in-prompt`** — computed at runtime (a catalog, a registry, a
  per-unit allow-list): render the list into the prompt at call time **and**
  validate in-loop with an error naming the legal values. Never enforce a
  runtime set with a static type: an approved catalog entry becomes a legal
  value the schema rejects.
- **`runtime-enum-injected`** — a runtime set injected into the emitted schema
  at call time. Nullable kills it (at least one provider's schema transform
  drops the enum), and a field may take this route only after its chain's
  enum survival is measured by the transport canary
  (`.agents/rules/provider-schema-transport-fidelity.md` owns that
  verification).
- **`file-authored-prompt`** — no schema in the producing path (the model
  authors a file directly): the prompt is the only route, and it must
  enumerate the set. One worked example is not delivery; it teaches the shape
  and hides the vocabulary.
- **`no-route-reachable`** — the declared escape for a field no delivering
  route reaches. Assigned explicitly, never by omission — and it carries a
  handling choice (reorder, declare open, or defer validation), never a
  silent lack of delivery.

An enum field must not be nullable. Measured through the model-routing
layer: at least one provider's schema transform discards the enum of a
nullable field — so on that leg the delivery route silently does not exist.

## Fail loud, never invent, never swallow

When no legal value fits, the run stops with an error naming the field, the
rejected value, and the full legal set. No sentinel escape value, and no broad
exception handler absorbing a contract violation into a degraded result — a
plausible wrong artifact travels further than a stopped run.

If the vocabulary itself is genuinely missing an entry, route that to the
subsystem that owns adding one, rather than letting a model mint it inline.

## How to apply

Before adding or reviewing any LLM-produced field, answer three questions:

1. **Is the set closed?** Anything checked with `not in`, a frozenset, a
   registry lookup, or a dict subscript keyed by model output is closed.
2. **Which of the five routes delivers it, and does that route actually
   run?** Verify with a caller search, not by reading a function's name — the
   two orphaned renderers behind this rule both looked live.
3. **What happens on violation?** Silent degradation is the worst outcome and
   the hardest to see; state the consequence explicitly.

## Against the neighbouring rules

`root-cause-before-guardrails.md` explains why the fix is delivery rather than
a better error message: the check is not the bug. `no-unjustified-fallbacks.md`
covers the swallowing half — a fallback that hides a contract violation reports
nothing and ships something wrong.
