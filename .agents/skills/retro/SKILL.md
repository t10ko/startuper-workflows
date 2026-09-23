---
name: retro
description: End-of-session reflection that turns real session signals (corrections, recurring review findings, friction, surprises) into durable, repo-shared knowledge — proposed .agents/instincts/ entries or MEMORIES.md lines. Always asks before writing anything; never persists automatically. Use when the user says "retro", "wrap up", "what did we learn", "capture learnings", "log this as a lesson", or after a non-trivial session/PR lands.
disable-model-invocation: true
---

# retro

Turn what actually happened in this session into knowledge the *next* session (any developer, not just you) benefits from. This is the manual, always-ask counterpart to `continuous-learning-v2`'s automatic hook — its capture pipeline isn't wired into `.claude/settings.json` in this repo, so this skill is the deliberate path until/unless that's fixed.

## When to use

- The user asks for a retro/wrap-up.
- A PR just landed and the session revealed something non-obvious.
- The user corrected you, or you had to work around ambiguous/missing guidance.

## When NOT to use

- Nothing notable happened. Say so; don't manufacture findings to fill a template (see anti-patterns).
- Mid-task, before anything has landed.

## Steps

### 1. Gather concrete signals

Read back over the session. Look for:
- **User corrections** — "no, do it this way" moments. Highest signal.
- **Recurring findings** — the same class of issue flagged more than once.
- **Friction** — a skill/rule/workflow's guidance was ambiguous, missing, or wrong.
- **Surprises** — something discovered that planning didn't anticipate.

Be concrete: "the `tdd-guide` workflow referenced `npm test` in a `uv`-only repo, cost a wrong command attempt" is usable. "Testing could be better documented" is not — drop it.

### 2. Sort into buckets — this decides where it lands

- **Repo-shared lesson** (`.agents/instincts/personal/*.yaml`) — a defect/gap that would bite *any* developer or agent working in this repo, not specific to one person's taste. Litmus test: would a different developer hit the same problem? Yes → this bucket.
- **User preference** (project `MEMORIES.md`, per `AGENTS.md` §15) — a preference about how *this specific user* likes to work, not a universal defect (e.g. communication style, review depth).
- **Not worth recording** — a one-off, already covered elsewhere, or too vague to act on. Say so and stop.

Don't conflate them: filing a personal preference as a repo-wide instinct overfits shared knowledge to one person; filing a real defect as a memory-only note hides it from the rest of the team.

### 3. Check for duplication before proposing anything

```bash
grep -rn "<keyword>" AGENTS.md .agents/rules/ .agents/instincts/
```

If root `AGENTS.md` or `.agents/rules/python-antipatterns.md` already states the lesson, the fix is pointing the model at the existing rule more prominently (or nothing) — not a new instinct file. New instincts should carry information *not already in AGENTS.md*, matching the standard this repo already holds (see the trimmed `.agents/instincts/personal/` set — no entry duplicates a root-doc rule).

### 4. Propose — never write silently

Show the user the exact proposed content before writing anything:

- **New instinct** — full YAML in the existing schema:
  ```yaml
  ---
  id: <kebab-case-id>
  trigger: "When working on <domain>"
  confidence: 1.0
  domain: "<domain>"
  source: "session-retro"
  scope: project
  ---

  # <Title>

  ## Action
  <the concrete rule>

  ## Evidence
  Context: <what was happening>
  Problem: <what went wrong without this>
  ```
- **New MEMORIES.md line** — the exact bullet, following the existing one-bullet-per-entry format.

**Wait for explicit confirmation on each proposed item before writing it.** This is not optional — the investigation this skill is based on was explicit that nothing should be logged automatically. If the user doesn't respond or declines, don't write it.

### 5. Write only what was confirmed

Write confirmed instinct files under `.agents/instincts/personal/` and confirmed lines to `MEMORIES.md`. These are working-tree edits only — this skill does not commit or push on its own, regardless of what `.agents/hooks/block_git_mutations.py` currently allows (`git add`/`git commit` are no longer hook-blocked, but `git push` still is, and this skill leaves all git writes to the human either way). Say so in the report.

## Report

- What was logged (repo-shared instinct / user memory), and where
- What was proposed but declined
- What was considered and dropped as not worth recording, with why
- Confirm nothing was committed — the human commits when ready

## Anti-patterns

- **Manufacturing feedback to fill a template.** If the session was clean, say so plainly.
- **Writing without confirmation.** Every persisted item must be explicitly approved first.
- **Duplicating AGENTS.md.** Check Step 3 before proposing — a new instinct that restates an existing rule is noise, not knowledge.
- **Misrouting a personal preference as a repo-shared lesson**, or vice versa. Use the Step 2 litmus test.
