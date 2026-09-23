---
description: Root-cause-analysis workflow — asks "why" repeatedly with evidence until a fundamental cause is found, fans out across independent problems, and reports the result in chat, offering a deliberation note only on explicit request.
---

# Root Cause Analysis Workflow

Use this workflow when something went wrong — a bug, a test failure, an
incident, or an autonomous iteration-loop run that misbehaved — and the cause
is not yet understood.

## Core Rule

No fix is proposed before the cause is understood — root-cause investigation
comes first, always. Keep asking "why", each answer backed by evidence (a log
line, a diff, a file:line, a transcript excerpt), until the answer is
actionable, preventable, and fundamental — not a fixed number of iterations.

## Workflow Steps

1. **Scope the problem(s)**
   - Take the user's free-text description of what happened.
   - Decide whether this names one problem or 2+ independent ones, using
     `.agents/workflows/deliberation.md`'s own scoping rule: split into
     separate decision items when there is more than one root-cause thread.

2. **Gather evidence per problem**
   - Investigation means reading the error carefully, reproducing it if
     possible, checking recent changes, and tracing the data flow.
   - Ralph-Loop evidence, conditionally: **if a Ralph-Loop state file exists
     at `.claude/ralph-loop.local.md`**, treat it as an evidence source — it
     is present only while the loop is still stuck or crashed (deleted on
     clean exit). Read `iteration`, `max_iterations`,
     `completion_promise`, and the original prompt from it, and locate the
     session transcript it points at (the JSONL passed as `transcript_path`
     to the loop plugin's Stop hook, or locatable via the state file's
     `session_id`) — the closest thing such a plugin produces to a loop log.
     **If the state file does not exist, skip this source entirely.**
   - Either way, when a loop was involved, use git history and working-tree
     diffs across the loop's iterations as primary evidence of what each
     iteration actually changed — such loops rely on files and git history,
     not fed-back output.
   - Only pull in loop-specific sources when the problem
     description or available state actually points to one; otherwise gather
     evidence the normal way (logs, tests, error output, git history).

3. **Fan out when 2+ independent problems are named**
   - Follow `.agents/AGENTS.md`'s Agent Orchestration section: dispatch one
     investigator agent per independent problem domain, all issued in the
     same turn so they run concurrently — **at most N concurrent agents**
     (N from `.agents/config.toml`, `[worktrees] max_concurrent`). With
     more independent problems than N, dispatch in batches of ≤ N — a
     queued batch starts as soon as a slot frees (one completion or one
     merge), never only after the whole running batch drains.
   - Each investigator is read-only (no file edits) and returns its own
     evidence-backed why-chain and candidate root cause.
   - The lead reconciles: resolve disagreement from source evidence, never by
     averaging across investigators.

4. **Deliver the result in chat, then offer a deliberation note**
   - Run the `critical-thinking` skill's (`.agents/skills/critical-thinking/SKILL.md`)
     bounded critical-thinking round per item, as `deliberation.md` already requires.
   - Present the root cause, evidence, and recommended direction per item in the
     reply. This workflow never writes to `docs/decision-notes/` on its own —
     see `.agents/workflows/deliberation.md`'s
     "Note Creation Is Never Automatic".
   - Ask with `AskUserQuestion` whether to record a note. Only on an explicit
     yes, follow `deliberation.md` exactly for the format: one `D1`/`D2`/... item
     per fixed decision, written to
     `docs/decision-notes/YYYY-MM-DD-<session-slug>.md`.
   - When a note is approved, genuinely independent problems get separate notes,
     and facets of one shared root cause stay as multiple items in one note —
     this is `deliberation.md`'s own note-scoping rule, not a new one.

5. **Stop at the decision — do not implement a fix**
   - The finding is the root cause, evidence, and a recommended direction per
     item. This workflow does not edit production code.
   - If you want to act on the finding, hand off to
     `.agents/workflows/detailed-plan.md`, exactly as `deliberation.md`'s own
     transition step already does.
