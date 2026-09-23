---
trigger: glob
globs: "agentic_workflows/**"
paths:
  - "agentic_workflows/**"
---

# Provider Schema Transport Fidelity

Recorded 2026-07-28, at the user's explicit request, after the same class of
failure was root-caused in this repository for the fourth time.

## The rule

**A JSON Schema this repo constructs is not the schema the model receives.**
Never assume a schema feature survives the trip to a provider. Before relying
on any schema construct to enforce a rule on model output, verify against that
provider's own documented schema subset — and verify it for the *specific model*
in the configured chain, because support differs by model generation.

If a construct is not verified to survive transport, the rule it was meant to
enforce **does not exist**, no matter how correct the Pydantic model is. Either
state the rule in prose the model actually reads, or fail loudly at the
conversion boundary. Silently converting a constraint away is the failure this
rule exists to stop.

## Why this keeps happening

Three separate layers can rewrite a schema between a Pydantic model and the
wire, and each one is allowed to drop what it does not understand:

1. Pydantic's own `model_json_schema()` output.
2. This repo's converter in `agentic_workflows/json.py`.
3. The agent library's converter, which runs last and is outside this
   project's own source.

None of the three raises when it discards a constraint. A discriminated union,
a `minLength`, an `additionalProperties: false`, or a type-union can be present
in the model, absent on the wire, and still enforced by a local Python
validator — so the model is rejected for breaking a rule it was never shown,
and the repair budget is charged for it.

`.agents/rules/no-overfitted-fixes.md` covers the adjacent mistake of
generalising from one example; this rule covers assuming a *declaration* is a
*delivery*.

## The concrete finding that prompted this (Gemini, verified 2026-07-28)

Verified from Google's own documentation plus multiple independent bug reports
against different client libraries. **Not verified by a live call from this
repo** — see "What is still unmeasured" below.

- **`anyOf` IS a supported attribute** in Gemini function-declaration parameter
  schemas, listed alongside `type`, `nullable`, `required`, `format`,
  `description`, `properties`, `items`, `enum`, `$ref`, and `$defs`. Support
  for `anyOf`/`$ref`/`$defs` arrived with the November 2025 JSON Schema update.
- **But `anyOf` must be the only field set on the schema object carrying it.**
  A sibling `type`, `description`, or `properties` on the same node is a hard
  400:

  > `Unable to submit request because <tool> functionDeclaration parameters.<field> schema specified other fields alongside any_of. When using any_of, it must be the only field set.`

  This is valid JSON Schema and is rejected anyway. It is a Gemini-specific
  constraint, not a standards issue.
- **Model generation matters.** Gemini 2.0 Flash did not support `anyOf` at
  all; the currently configured chains' models are past that update — but a
  future chain edit can silently reintroduce an unsupported model.
- **The sibling rule interacts badly with descriptions.** Stripping siblings to
  satisfy Gemini deletes the `description` on that node, which is exactly the
  channel this repo would otherwise use to state a rule the schema cannot
  carry. Fixing the union and keeping the description are in direct tension,
  and the resolution must be chosen deliberately rather than discovered.

## What is still unmeasured

Documentation confirms the API *accepts* the construct. It does not tell us:

- whether the real schema is accepted at real size — one existing tool
  already emits roughly 1,150 tokens of schema against a 12,000-token
  per-message ceiling, and a multi-branch union multiplies the per-prop object;
- whether **compliance** improves, not merely acceptance — a schema the API
  takes but the model ignores fixes nothing;
- whether type-lists, length limits, and extra-field bans survive once a
  converter is patched, since those four transport losses are independent of
  unions;
- how the Anthropic failover path behaves, which matters because a configured
  chain can fail over mid-run.

Those remain the empirical questions to answer for any newly configured
chain, per scenario-style probes: acceptance at real size, compliance, the
four independent transport losses, and failover behavior.

## How to apply

- Before using a schema construct to enforce a rule on model output, check the
  provider's supported-attribute list for the configured model, and check
  whether the construct carries usage constraints of its own (mutual exclusion,
  nesting depth, size).
- When a converter drops a construct, that must produce a loud, attributable
  signal. A converter that silently discards a declared constraint is the
  defect, not the model's non-compliance.
- Never charge an agent's repair budget for violating a constraint that
  provably never reached it.
- Record the verification date and the model generation alongside any claim
  about provider schema support. These change; a claim without a date is not
  evidence.

## Sources

- [Function calling with the Gemini API](https://ai.google.dev/gemini-api/docs/function-calling)
- [Introduction to function calling — Google Cloud](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/tools/function-calling)
- [JSON Schema support in the Gemini API](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-api-structured-outputs/)
- [langchain-google issue 1216 — other fields alongside any_of](https://github.com/langchain-ai/langchain-google/issues/1216)
- [opencode issue 14700 — anyOf schema violation](https://github.com/anomalyco/opencode/issues/14700)
- [gemini-cli issue 13326 — `$defs` references rejected](https://github.com/google-gemini/gemini-cli/issues/13326)
