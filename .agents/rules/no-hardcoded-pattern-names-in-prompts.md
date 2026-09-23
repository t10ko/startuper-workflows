---
trigger: glob
globs: "**/*.py,**/*.md"
---

# No Hardcoded Pattern Names in Prompts

Recorded 2026-07-14 from a live session.

## The rule

Never write prompt or instruction text that special-cases a specific
structural pattern by name (e.g. "a heading", "a table", "a caption line")
as if naming it were the fix. Instead, teach the model to recognize the
general underlying concept — "is this a reusable structural template, not
yet delivering content" — and cite one pattern (a title/heading) only as an
illustrative example, never as the covered case.

**Why:** This was said explicitly early in a design session ("your
suggestion regarding how to choose a structural boundary, including
mentioning titles explicitly, isn't good, it's an overfitting, there can be
many more such cases") and had to be repeated a second time
later in the same session when a prompt draft reintroduced
hardcoded language naming "a heading, a section title, a caption line, or
an unexplained table/list" directly. Naming specific structural types in a
prompt is the exact same overfitting failure as hardcoding them in code —
every future pattern that isn't named (a subheading, an epigraph block, a
footnote, a numbered step) stays uncovered, and the prompt looks fixed
while the underlying blind spot persists.

## How to apply

When drafting or reviewing any prompt or instruction text for a project
(review prompts, extraction prompts, or any other `.md` prompt
file under a `prompts/` directory), scan for call-outs of specific
chunk/content kinds by name. If found, rewrite as a general, reusable
concept the model can apply to any structural pattern, and demote the named
example (e.g. "a title is one obvious case") to illustration only — never
the rule itself. This applies to every layer of a design that touches
structural boundaries (e.g. structural-boundary detection), not just
whichever single draft triggered the feedback.
