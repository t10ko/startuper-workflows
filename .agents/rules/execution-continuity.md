---
trigger: always_on
---

# When to keep going without checking in

- Once a plan or multi-step request is approved, continuing it is the default action every turn — not a fresh decision to re-open. Approving a plan's scope approves its pace too, unless the human said otherwise.
- Exactly three things justify stopping mid-plan: a blocked status you cannot resolve yourself, a decision genuinely outside what the plan already settled — a new behavior, UX choice, deliverable, or architecture direction — or the whole approved plan is done. Nothing else does. Stopping for that second reason means actually asking the question, per AGENTS.md's own HITL rule — not silently picking a default and moving on.
- "This feels like a natural checkpoint," "my context is getting long," "the remaining scope is large," and "the human should decide whether I continue" are not on that list. Long sessions are summarized automatically — that is not something to manage by ending the turn.
- Never end a turn by asking whether to continue, offering to continue, or describing what you would do next instead of doing it. If none of the three reasons above applies, the next words are the next tool call, not a question about one.
- A blocker that only affects a later, not-yet-reached part of the plan is not a reason to stop now — keep working on what is unblocked and flag the future blocker when you actually reach it.
- If you write "continuing" or "still going," the next thing in the same turn is the tool call that does it, not the last line of the message.
- This governs your own pace executing an approved plan. It is separate from AGENTS.md's Iterative Execution / NOTHING AT ONCE rules, which govern the content pipeline's own unit-at-a-time processing, not how you pace your own plan execution.
- A real blocker still costs nothing to name and stop for. This file narrows nothing about that.
