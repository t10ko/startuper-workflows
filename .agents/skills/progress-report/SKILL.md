---
name: progress-report
description: Use whenever an executing workflow or plan run reports progress to the user — once per orchestrator turn that changes task, group, or run state; never a turn created solely to report. Sole owner of the Aligned Horizontal Timeline Progress Bar, its concurrency lanes, and its exact fill arithmetic (round(P/100 x 20) filled blocks on a 20-character bar). Invoke before drawing any progress bar — never restate the layout elsewhere.
---

# progress-report

The single owner of the plan-run progress report: the Aligned Horizontal
Timeline Progress Bar, its layout, and its exact character math. Workflows
that must report progress invoke this skill; none of them restates the
layout or the arithmetic in their own files.

## When to invoke

**Once per orchestrator turn that changes task, group, or run state — and
never in a turn created solely to report.** Harvesting a completion,
dispatching eligible work, landing a merge, entering or clearing a Blocked
state, entering the integration phase — each is a state change, and the
turn that makes one closes with a bar; a turn that only reads state emits
none. Invoke the skill rather than drawing a bar from memory: a bar guessed
from memory is how a 32% bar comes out 19 blocks full, and a
context-compacted session has no memory of this format at all — the
invocation is what re-loads it.

**Never create a turn solely to report or poll.** The bar rides a turn that
already changed state, at zero extra orchestrator turns; a report-only turn
is billed the full depth of the accumulated context
(`.agents/rules/sizing-agent-work.md`) and does no work of its own. A turn
with no state change to show draws no bar — the bar's numbers would not
have moved, because nothing completed.

**The floor this does not lower:** a state transition still reports
immediately, in the turn that transitions it — a blocked group, a failed
merge, or a halt the human must act on is never held back to a later turn.
The run's closing turn still emits the final 100% report.

## Placement

Emit the bar as the **last block of the turn's final message** — never
between tool calls. Harnesses differ in what they render mid-turn; the
closing message is the one channel every harness shows.

## Required Layout Format

```text
Overall Plan  : [████████░░░░░░░░░░░░░░░░]  23% (9/50 tasks complete)
Plan Timeline : 0% ────────────────────── 100% (Task 1 ➔ Task 50)
┌─ Concurrency Lane 1 (Parallel Track A)
│  ├─ Grp A [T1-T10]   : [████████████████████] 100% [DONE] (Merged into integration)
│  └─ Grp C [T11-T25]  : [████████░░░░░░░░░░░░]  40% [LIVE] (Task 16 • in review)
├─ Concurrency Lane 2 (Parallel Track B)
│  ├─ Grp B [T26-T35]  : [███████░░░░░░░░░░░░░]  35% [LIVE] (Task 29 • implementing)
│  └─ Grp D [T36-T45]  : [░░░░░░░░░░░░░░░░░░░░]   0% [WAITING] (Waiting for Grp B)
├─ Concurrency Lane 3 (Parallel Track C - Independent)
│  └─ Grp E [T46-T48]  : [████████████████████] 100% [DONE] (Merged into integration)
└─ Final Integration   : [░░░░░░░░░░░░░░░░░░░░]   0% [QUEUED] (verify_cmd & PR)
Status        : 9/50 tasks complete • 2 agents live • 1 track waiting
```

## Layout Rules & Exact Character Math

1. **Entire Plan Representation Invariant**: The progress display MUST always represent the **entire plan from start to finish** (all groups from Group 1 to Group N, and Final Integration). Never emit a partial subset or omit queued/completed groups.
2. **Parallel Concurrency Lanes vs. Sequential Chains**:
   - Distinct **Parallel Concurrency Tracks / Lanes** (`Concurrency Lane 1`, `Lane 2`, etc.) MUST be visually separated to clearly convey parallel execution.
   - Within each lane, sequential dependency chains (e.g. `Grp A ➔ Grp C`) are nested hierarchically under that lane, with clear status indicators (`[LIVE]`, `[WAITING]`, `[DONE]`, `[QUEUED]`).
   - Independent standalone groups form their own parallel lane.
3. **Fixed Bar Width Rule**: Every progress bar (`Overall Plan`, `Grp *`, `Final Integration`) MUST use a fixed total width of exactly **20 characters** inside `[...]`.
4. **Exact Character Calculation Invariant**: The visual fill MUST strictly match the stated percentage $P\%$:
   - $\text{filled\_count} = \text{round}\left(\frac{P}{100} \times 20\right)$ blocks of `█`
   - $\text{empty\_count} = 20 - \text{filled\_count}$ blocks of `░`
   - **Never guess character counts.** $32\%$ on a 20-slot bar is $6$ `█` and $14$ `░` (`[██████░░░░░░░░░░░░░░] 32%`), NEVER $19$ `█` ($61\%$)!
5. **Reference Conversion Table**:
   - $0\%$: `[░░░░░░░░░░░░░░░░░░░]   0%` (0 filled, 20 empty)
   - $13\%$: `[███░░░░░░░░░░░░░░░░░]  13%` (3 filled, 17 empty)
   - $23\%$: `[█████░░░░░░░░░░░░░░░]  23%` (5 filled, 15 empty)
   - $27\%$: `[█████░░░░░░░░░░░░░░░]  27\%` (5 filled, 15 empty)
   - $35\%$: `[███████░░░░░░░░░░░░░]  35\%` (7 filled, 13 empty)
   - $40\%$: `[████████░░░░░░░░░░░░]  40\%` (8 filled, 12 empty)
   - $50\%$: `[██████████░░░░░░░░░░]  50\%` (10 filled, 10 empty)
   - $60\%$: `[████████████░░░░░░░░]  60\%` (12 filled, 8 empty)
   - $100\%$: `[████████████████████] 100\%` (20 filled, 0 empty)
6. **Plan Timeline Ruler**: Spans exactly 20 characters between `0%` and `100%` (`0% ────────────────────── 100% (Task 1 ➔ Task N)`), perfectly aligning with the opening `[` and closing `]` brackets.
7. **Track Label Indentation**: Pad track label prefixes so all opening brackets `[` align at the exact same horizontal column.
8. **Overall Plan Progress Line**: Shows total progress percentage calculated from completed and in-flight work units across all $N$ tasks in the plan:
   - **Total Work Units ($W_{total}$)**: Total tasks across all groups + 1 integration phase unit.
   - **Completed Units ($W_{done}$)**: Completed reviewed tasks ($1.0$ each) + merged group bonus ($0.2$ each) + in-flight task credit ($0.5$ for implementing, $0.75$ for reviewing).
   - **Formula**: $\text{Progress \%} = \min(99, \lfloor (W_{done} / W_{total}) \times 100 \rfloor)$. $100\%$ is reserved for final PR creation and verify pass.
9. **Status Summary**: Single concise line showing completed task counts across the whole plan, live subagents, and waiting dependency tracks.

## Single ownership

This skill is the only place the bar's layout and arithmetic live. A
workflow that needs progress reporting points here and invokes
`progress-report`; it never copies the layout, the rules, or the conversion
table into its own references — a copy drifts the first time one of the two
is edited, and a compacted session cannot tell which copy it remembered.
