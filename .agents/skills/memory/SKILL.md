---
name: memory
description: >
  Manages project memories in MEMORIES.md. Adds entries ONLY when explicitly asked.
  Never auto-records. Use when user says "remember this", "add to memory", "save this rule",
  or "update MEMORIES.md". On read-back, surfaces relevant entries silently when starting a task.
---

# Memory Skill

## Core Rule

Consent requirements for writing to `MEMORIES.md` are defined once, canonically,
in `.agents/rules/memory-consent.md` — follow that rule. This skill covers only
the mechanics specific to `MEMORIES.md` itself.

Triggers that count as explicit consent for a `MEMORIES.md` write: "remember
this", "add to memory", "save this rule", "note this", "update MEMORIES.md".
No other phrase causes a write. Inferred importance is NOT a trigger.

## Where a Learning Belongs

Before writing, pick the right destination — they are not interchangeable:

- A standing behavioral rule (should shape future behavior broadly) belongs in
  `.agents/rules/` as its own file.
- A terse, project-specific one-liner belongs in `MEMORIES.md` (this skill).
- An unfixed issue or open question belongs in the project's own gap/issue tracker — `.agents/open-gaps.md` where the project keeps one (requires explicit user approval via a standalone question before writing).

## File Location

`MEMORIES.md` in the project root.

## Format

Each memory is a single bullet — short, actionable rule. No narrative.

```
- <concise rule>
```

Bad: "I learned that when you run the tests using pytest they sometimes fail because of import issues."
Good: "Always run `python3 -m pytest` from the project root, never from subdirectories."

## Adding a Memory

1. Read `MEMORIES.md` to avoid duplicates.
2. Append the new bullet under the existing list.
3. Confirm: "Added to MEMORIES.md: `<rule>`"

## Reading Memories

At the start of any relevant task, silently scan `MEMORIES.md` and apply matching rules.
Do not announce the scan unless a memory directly changes behavior.

## Deduplication

Before writing, check if an equivalent rule already exists. Merge or skip rather than duplicate.
