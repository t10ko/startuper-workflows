# Task specification and design workflow — design notes

Dated design history, incident records, and measurement records moved out of
`SKILL.md` (2026-08-23), so its body carries only live workflow instructions
and guard-rationale. Each section below preserves its record's content from
the origin site; `SKILL.md` leaves a one-line pointer at each origin.

## The delegation tool-call budget measurement

A tool-call budget in a delegation prompt was tried and withdrawn on
measurement: across 562 read-only agents, tool calls run to a median of 25
and a p90 of 48, so a 15-call cap truncated 75% of them. Its 20.6% saving
was a replay that deleted every record past turn 15 and re-priced; it proved
the arithmetic, never that the work still finished.

## The grounding artifact file-read measurement

The shared grounding artifact mirrors what `code-review-fix-loop` already
does with its one diff snapshot that every reviewer reads, and it exists
because 66.4% of all file-read volume across this repo's agent sessions is
a file another agent in the same session had already read.
