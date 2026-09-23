# Parallel subagent-driven development — design notes

Dated design history, incident records, and measurement records moved out of
`SKILL.md` (2026-08-23), so its body carries only live workflow instructions
and guard-rationale. Each section below preserves its record's content from
the origin site; `SKILL.md` leaves a one-line pointer at each origin.

## The single-group cost gap

The single-group fast path — one worktree only, doubling as the integration
worktree — was first only a design, not implemented: as the steps were
originally written, every group, including a lone one, got its own worktree
distinct from the run's integration worktree. The outcome is correct either
way (a pushed branch, an opened PR), but a single-group run paid the full
multi-group mechanical cost until that gap was closed by the fast path now
defined in `run-start.md` and `landing-and-pr.md`.

## The two proportionality-shaped failures

The two confirmed failures that made this workflow's invocation
unconditional in the first place were both proportionality-shaped: a
group-count precondition nobody ever computed, and a plan-authored sentence
calling one part of a run "optional, not load-bearing."

## Change 5 and the `ab15c333` regression

This is the rule a 2026-08-04 cost-control plan's Change 5 accepted and
shipped on 2026-08-05, which commit `ab15c333` dropped two days later while
modularizing `detailed-plan.md`, unrecorded.

## The 1,077-turn runaway-implementer measurement

Measured consequence of its absence: a single implementer at 1,077 turns in
one context grown to 772k tokens with no compaction, billing 553.8M
cache-read tokens to re-read ~210k tokens of content it had already seen.

## The 2026-08-08 quota-exhaustion incident

The 2026-08-08 LLM migration hit 17 concurrent agents and exhausted the
5-hour quota.

## Step 3.5: (removed — per-group code-review-fix-loop eliminated)

Per-group `code-review-fix-loop` passes are eliminated. This is not the
per-group task review Step 2 schedules: that one is the inner loop's own
reviewer covering the group's tasks in one pass, while the thing removed here
was the heavyweight multi-reviewer `code-review-fix-loop` skill run a second
time per group. The spec+quality review inside the inner loop (Step 2) already gates individual
task quality, and the single integration-level `code-review-fix-loop`
(Step 7) reviews the full consolidated diff — catching every finding a
per-group pass would have made, plus cross-group interactions a per-group
pass structurally cannot see.

A group advances directly from `InProgress` (all tasks complete and
task-reviewed) to `AwaitingMerge`. The `GroupReviewPending` state and the
`ConflictHalted(Overlap)` sub-state no longer exist.

**Superseded 2026-09-17:** the next two paragraphs describe the
patch-apply landing that has since been removed. The overlap pre-flight and
the serial-apply queue no longer exist: groups land by rolling
dependency-order branch merges as each completes, an overlap surfaces as a
native merge conflict on Step 6's conflict path, and
`ConflictHalted(Overlap)`'s successor is `ConflictHalted(Landing)`. Kept
only as the history of the mechanism between 2026-08 and 2026-09.

The actual-diff-overlap check that ran here now runs as Step 6's pre-flight,
before landing. See Step 6 for the exact mechanism.

If 2+ groups become eligible for landing in the same orchestrator turn,
queue them for the still-strictly-serial apply step (Step 6) in **ascending
group-ID order** — a fixed, deterministic tie-break, not first-noticed-first-
served.

## Step 5: (removed — see Step 6)

The actual-diff-overlap check now runs as Step 6's pre-flight, before
landing. See Step 6 for the exact mechanism. (Superseded 2026-09-17 by
rolling branch merges — see the note under Step 3.5 above.)

