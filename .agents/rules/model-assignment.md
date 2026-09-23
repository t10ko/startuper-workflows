---
trigger: always_on
---

# Which Model Every Subagent Gets

This file is the **only** place in this repository that decides which model a
dispatched subagent runs on. No plan, spec, brief, skill, workflow, group, tier
table, escalation ladder, or agent definition may state, raise, lower, or
override a model choice. If another file appears to, that file is wrong and is
fixed by deleting its copy and linking here — never by reconciling the two.

Recorded 2026-09-12 at the user's direction, after measurement showed 93% of
implementer subagent turns ran on the deepest tier, costing roughly a quarter
of a week's usage limit, because a plan's per-group tier table was permitted to
raise the implementer above the model its own definition pinned.

## The rule, in tiers

Three tiers, named by capability rather than by any harness's product names:
the **cheapest tier**, a **standard-capability model**, and a **deeper model**
(up to the deepest). Each harness maps these tiers onto its own model lineup —
Claude Code per its model names, ZCode per its configured models.

**1. The cheapest tier is never assigned to any subagent role.** Any version,
any role, no exception.

**2. An implementation role runs a standard-capability model. Always. There is
no exception, no approval that grants one, and no condition that creates one.**

An implementation role is any subagent whose output changes project source —
a source file, a test, a script, a prompt file, a config file, or any other
file that is part of the product rather than a description of it.
`sdd-implementer` and `code-simplifier` are implementation roles today.

**3. An investigation role runs a standard-capability model by default, and
may run a deeper model when the dispatcher states a concrete reason in the
dispatch prompt — except the review roles whose own definitions pin a deeper
model: `silent-failure-hunter`, `security-reviewer`, `type-design-analyzer`,
and `pr-test-analyzer`. That list is the definition-pinned exception class
this rule owns; it changes here and in the definitions in the same diff,
never in one store alone. The deepest tier is investigation-only: no role
that writes project source ever runs on it.**

An investigation role is any subagent whose only output is findings — a report,
a review, a plan, a scenario set, a diagnosis — written to its own notes file
and to nothing else. Scouts, analysts, critics, reviewers, debuggers, and
`Explore` agents are investigation roles.

**4. The agent definition's `model:` field is the whole mechanism.** A dispatch
passes no `model` argument for an implementation role, ever. For an
investigation role, a dispatch may pass the deeper model only under rule 3.

## Why an implementer never needs the deepest tier

By the time an implementer is dispatched, a detailed plan already exists. The
analysis, the edge cases, the contracts, the file inventory, and the acceptance
criteria were all settled during planning, by a session that was allowed to
think as hard as it needed to. The implementer's job is to carry out a decided
change against named files with a stated test command.

If a task genuinely seems to need the deepest tier to implement, that is not a
signal to raise the model. It is a signal that the plan did not decompose the
work far enough, and the correct repair is to split the task in the plan.

## How to apply

Before writing anything that assigns, suggests, or implies a model:

1. Ask whether the subagent's output changes project source or only records
   findings; that single question decides the tier.
2. If it changes project source, write no model anywhere — the agent
   definition's pinned standard-capability model is already correct and
   complete.
3. If it only records findings and a deeper model is genuinely warranted, put
   the reason in the dispatch prompt itself, in one sentence.
4. Never introduce a tier name beyond the three above, a level, a floor, a
   ceiling, a class, or any other name for a model choice; those names are how
   a second owner gets created. Name harness model ids in agent definitions
   only, never in plans, briefs, or dispatch text.

## Against the neighbouring rules

`.agents/rules/single-source-of-truth.md` is why this file is the sole owner:
a model choice stated in a plan and again in an agent definition is two
writable stores of one value, and the drift between them is silent until a
usage bill shows it. `AGENTS.md` §14 is why the repair is collapsing to one
owner rather than keeping the copies in step.
