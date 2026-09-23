---
description: Explain in a simple manner
---

`.agents/rules/response-contract.md` is already active on every turn and governs how the reply is
written. This command changes only the *content*: the reply should explain how something works,
rather than report status or summarize a diff.

The one thing worth adding, because it is what makes explanations long: **answer only what was
asked.** Reading twenty files surfaces twenty true things, and nineteen belong to questions nobody
asked. "What does `x()` do and why does it exist" is two questions — what it does, why it exists.
Its callers, its internals, its error paths, and its history are four more.

**Subagents:** for broad multi-subsystem explanations only, use
`.agents/AGENTS.md` with max 2 read-only helpers. Lead writes the final
explanation; helper reports are addressed to the lead, not the user, and are exempt from the
contract's message-shape rules.
