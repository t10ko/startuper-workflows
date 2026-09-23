---
description: Evidence-backed decision-making workflow for structured sessions with strict notes, diagrams, critical-thinking review, and durable follow-up records.
---

# Deliberation Workflow

Use this workflow when the user wants to think through a product, architecture,
prompt, contract, UX, reliability, or implementation decision before coding.

The output is a tracked deliberation note under `docs/decision-notes/`.
If the user asks for a separate root decision document, create or update that too.

## Note Creation Is Never Automatic

Creating or editing any file under `docs/decision-notes/` requires the user to
have asked for it. Exactly two things satisfy that condition:

- **The user explicitly invoked this workflow** — `/deliberation`, or a direct
  request to deliberate on something or to record a decision note. That
  invocation *is* the request: write the note at step 5 without asking again.
- **The user gave an explicit in-session go-ahead** after being offered a note.

Every other path stops short of the file. Another workflow reaching this one, an
agent judging that a decision "deserves" a record, a decision surfacing mid-task,
a session that merely resembles a past deliberation — each delivers the analysis
in chat and asks with `AskUserQuestion` before touching `docs/decision-notes/`. A
"no" ends it and the reasoning stays in chat. Never write the note first and
offer to remove it afterward.

## The Other Thing This Directory Holds

`docs/decision-notes/` is also the **only** place a noticed-but-unfixed finding
may be recorded — a defect outside the current scope, a gap no task owns, a
guard that cannot fire, a spec claim measurement contradicted. Not a code
comment, not a plan, not a run-state file, not a commit message. The rule and
its reasoning are `.agents/rules/findings-go-in-decision-notes.md`.

Such a register is a decision note like any other: the same approval gate above
applies, and one note may carry many findings. It differs only in shape — it
records what is wrong and unowned rather than what was decided, so its entries
carry a severity and a possible owner instead of a decision and a rationale.

If approval is not available in the moment, the finding is said in chat and left
out of the code entirely. A finding stated and lost beats one buried in a
comment and mistaken for coverage.

## Core Rule

Do not treat discussion as disposable chat. Convert important reasoning into a
small, durable note that future debugging can read.

Deliberation notes are not plans. Keep them short, direct, and decision-first.
Target 300-900 words. A note represents one deliberation session or one tightly
related decision family. The whole note body must be a single list of decision
items: `D1`, `D2`, `D3`, and so on. Do not create global Evidence, Diagram,
Options, Cleanup, or Open sections outside the list. Do not merge a new decision
into an older item; append a separate decision item.

Every deliberation note must:

- use the strict format below
- contain a `## Decisions` section
- keep each fixed decision as a separate numbered item
- put evidence, diagram, options, critical-thinking summary, cleanup, and open
  items inside each decision item
- include at least one Mermaid diagram inside the list
- use `.agents/skills/critical-thinking/SKILL.md`
- separate evidence from assumptions
- name the owner boundary or source of truth
- list rejected options and why
- list cleanup work for contradictions
- state guardrails needed before implementation is trusted

## Workflow Steps

1. **Scope the deliberation**
   - Name the exact session topic.
   - Split the discussion into separate decision items when it contains more
     than one rule, contract boundary, product behavior, or architecture choice.
   - Keep each decision item narrow enough to validate from evidence.

2. **Collect evidence**
   - Use `rg` to find relevant code, prompts, docs, logs, schemas, tests, and
     generated artifacts.
   - Prefer local source of truth over memory or guesses.
   - Record exact files and line numbers in the note.

3. **Run critical-thinking workflow**
   - Invoke the `critical-thinking` skill (`.agents/skills/critical-thinking/SKILL.md`).
   - Run at least one bounded critical-thinking round.
   - Keep the full analysis in working context.
   - Put only the compressed result in the note: top risk, rejected options,
     source-of-truth choice, and remaining unknowns.

4. **Decide**
   - Pick one recommended direction per decision item.
   - Name the owner boundary.
   - Name the source of truth.
   - Explain why this direction is simpler and more reliable than alternatives.
   - If a new conclusion appears during review, add a new numbered decision
     item instead of editing it into an existing item.
   - If confidence is not high, stop at a provisional decision and list the next
     evidence probe.

5. **Write the note**
   - Only when "Note Creation Is Never Automatic" above is satisfied. Otherwise
     the analysis is delivered in chat and the file is not created.
   - Path: `docs/decision-notes/YYYY-MM-DD-<session-slug>.md`.
   - **A document body over 8,000 characters is written by a dispatched `document-writer`** (`.agents/specialists/document-writer.md`), which returns only the path it wrote and that file's byte size; the orchestrator then reads back only the sections it must act on. The threshold is exclusive: a body of exactly 8,000 characters is written by the orchestrator itself, and only a body above that reaches the writer. It decides who writes the document, never how long the document may be, and no real finding is ever trimmed, thinned, or dropped to land on either side of it.
   - Use the strict template below.
   - After the title, write only `## Decisions` and decision-list items.
   - Do not add global evidence, diagram, options, cleanup, or open sections.
   - Do not leave `TBD`, `TODO`, placeholder text, or empty sections.
   - If something is unknown, write `Unknown:` with the exact verification step.

6. **Self-review the note**
   - Check for contradictions, vague language, missing evidence, missing diagram,
     and missing guardrails.
   - Check that rejected alternatives are real options, not strawmen.
   - Check that cleanup work removes old contradictory contracts where possible.
   - Cut plan-like detail. The note must record the decision, not all future work.

7. **Transition**
   - If user wants implementation, move to `.agents/workflows/detailed-plan.md`.
   - If the decision touches whole-scope, one-unit-at-a-time processing, also
     use `.agents/workflows/architect.md` to preserve that architecture.

## Strict Deliberation Note Template

Use one file per deliberation session or tightly related decision family.
Prefer bullets over paragraphs. Do not include an implementation plan.

````markdown
---
status: accepted
date: YYYY-MM-DD
topic: short-session-topic
decision_owner: primary-subsystem-or-boundary
source_of_truth: primary-contract-or-owner
confidence: high
related_files:
  - path/to/file.py:123
related_workflows:
  - .agents/skills/critical-thinking/SKILL.md
---

# Deliberation: Clear Human Title

## Decisions

- **D1 - Clear Decision Title**
  - **Decision:** One sentence.
  - **Owner:** Boundary or subsystem that owns this rule.
  - **Source of truth:** Exact contract, model, artifact, or process.
  - **Rules:** 1-3 bullets.
  - **Evidence:** 2-4 bullets with exact file lines and meanings.
  - **Diagram:**

    ```mermaid
    flowchart TD
        A["Input"] --> B["Decision owner"]
        B --> C["Trusted output"]
    ```

  - **Options:** chosen option and rejected options, with short reasons.
  - **Critical-thinking summary:** checked assumption, main risk, guardrail, remaining uncertainty.
  - **Cleanup:** contradictions to remove or downgrade.
  - **Open:** unknown that could change this item, or `none`.

- **D2 - Clear Decision Title**
  - Use the same compact item format.
  - Add this only when the session has a second fixed decision.
````

## Reliability Bar

Use these confidence labels:

- `high`: evidence points to one owner boundary, tests or contracts can enforce it
- `medium`: direction is likely right, but one important probe remains
- `low`: do not implement yet; collect more evidence first

Never write a confident decision if the evidence is only a guess.
