---
trigger: always_on
---

# Root Cause Before Guardrails

Recorded 2026-07-22 from a live session.

## The rule

Don't propose a guardrail (validation check, guard clause, defensive check)
as "the fix" for confirmed buggy behavior without first identifying and
fixing the root behavioral cause. A check that only catches the symptom
after the fact is not a fix — it is a defensive patch layered on top of an
unfixed problem.

**Why:** In a debugging session, a guardrail was proposed (block a known-bad
empty state before commit, reject vacuous declared facts) for a
multi-stage generation-pipeline bug without first asking why the underlying
agent/model
behavior produced the bad state. The user pushed back with a clean test: if
fixing the root behavior wouldn't still need a guardrail, then fixing the
behavior IS the fix — guardrails are only for cases where the bad state can
still occur despite a correct root fix (e.g., inherently unpredictable LLM
output, untrusted input).

## How to apply

Before recommending a guardrail or validation check as a fix, explicitly
investigate the upstream cause of the bad behavior first — missing context
passed to a model, an ambiguous prompt or instruction, missing information
at generation time, a structural design gap. Fix that if it's fixable. Only
recommend a guardrail as an additional safety net afterward, and say
explicitly that it's a safety net rather than the fix, plus why it's still
warranted even after the root cause is addressed. Related:
`.agents/rules/no-overfitted-fixes.md` (fix generality) and
`.agents/rules/architectural-reliability.md` (root-cause-oriented design) —
this rule is specifically about sequencing: root-cause investigation and
fix must come before, not alongside or instead of, a guardrail proposal.
