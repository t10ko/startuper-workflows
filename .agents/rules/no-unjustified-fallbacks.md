---
trigger: glob
globs: "**/*.py"
paths:
  - "**/*.py"
---

# No Unjustified Fallbacks

Recorded 2026-08-08 at the user's explicit request, from a live session that
found a fallback in a scope-resolution pipeline whose alternate branch is
unreachable and whose behavior, if it ever did fire, would silently degrade
output quality rather than fail.

## The rule

A fallback, default, or backward-compatibility path must have a **real,
stated reason**. Write it only when you can name the concrete condition that
reaches it and say why continuing is better than failing. If you cannot name
that condition, do not write the fallback — let the code fail.

This is not a ban on fallbacks. It is a ban on fallbacks that exist because
they were easier than establishing what the contract actually is.

## Why, in the project's own terms

This is an MVP / Alpha. Seeing real problems as they arise is worth more
than surviving them quietly. A bug that surfaces gets fixed; a bug absorbed
by a fallback stays in the system, and the fallback makes it look handled.

That is the deeper harm: an unjustified fallback is not merely dead weight,
it is **concealment**. It converts a signal into silence, at the exact
moment the signal was most useful.

Two consequences follow, and both were observed in the triggering case:

- **The alternate branch is often unreachable**, so it is untested code that
  documents a contract the system does not actually have.
- **When it is reachable, it degrades instead of stopping.** Falling back to
  a "close enough" input produces a plausible wrong result, which is harder
  to detect than a crash and can travel a long way downstream before anyone
  notices.

## How to apply

Before writing a fallback, default value, `or`-chain, `try`/`except` that
swallows, or compatibility branch, answer all three:

1. **What concrete condition reaches this branch?** Name it. "In case
   something is missing" is not a condition. If nothing in the system can
   produce it, the branch should not exist.
2. **Why is continuing better than failing here?** If the answer is "so the
   caller doesn't have to handle it" or "so tests are easier to write", that
   is not a reason — fix the caller or the test setup instead.
3. **What does the fallback path produce, and is it correct — not merely
   non-crashing?** A fallback that yields a degraded-but-plausible result is
   worse than no fallback, because it hides rather than reports.

If all three have real answers, write the fallback and record the reasoning
in a comment or a spec decision. If any one does not, fail fast instead —
which is `AGENTS.md`'s existing "Fail fast on bad input" rule, applied to the
absence of input rather than to bad input.

## Consistency check

When one call site falls back and another raises on the same condition, the
codebase is holding two contradictory positions about whether that input is
required. One of them is wrong. Resolve it rather than leaving both.

## The triggering case

A `prepared_input or raw_input`-shaped fallback in a scope-resolution path.
Three findings, each independently sufficient:

- **Unreachable.** An upstream stage writes the prepared artifact for every
  input, unconditionally and ungated by language, and the loader raises
  when the artifact is absent. By the time the pipeline runs, the list is
  always populated.
- **Contradicted elsewhere.** Two other consumers treat the same empty state
  as an error, raising on the missing prepared input. The scope path alone
  disagrees, silently.
- **Degrades if it ever fires.** The prepared input is the processed,
  control-plane form of the content. Falling back to raw source feeds
  unprepared text to downstream LLM reasoning stages — a silent quality
  regression in boundary judgment, with no error and no log.

The honest shape is a required input: if the prepared input is absent, that
is a defect upstream and the run should say so.

## Related rules

- `.agents/rules/root-cause-before-guardrails.md` — a guardrail must not
  substitute for fixing the root behavior. This rule is the adjacent case: a
  fallback must not substitute for establishing the contract.
- `.agents/rules/architectural-reliability.md` — "Can any failure be
  eliminated by construction?" A required input that is always present by
  construction needs no fallback.
- `AGENTS.md` §1 MVP Contracts — "No backward compatibility, shims, or
  dual-paths. Fail fast on bad input."
