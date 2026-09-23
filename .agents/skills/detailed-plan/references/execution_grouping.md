# Execution Grouping, Thinking Tiers, & Subagent Driven Development Integration

This document defines task grouping rules, model/thinking tier assignment, and handoff to the `parallel-subagent-driven-development` skill.

## 1. Parallel-Safety Grouping Rules

Every plan decomposes work into ordered tasks grouped into task groups.
Each task group MUST be labeled:
- `Independent (parallel-safe)`
- `Sequential (must follow <group-id>)`

### Grouping Verification Command
Use `.agents/scripts/parallel_plan_grouping.py`'s `label_groups()` to validate file overlap and `Consumes`/`Produces` interface collisions:

```bash
python3 -c "
import sys; sys.path.insert(0, '.agents/scripts')
from parallel_plan_grouping import label_groups, Task
print(label_groups([Task(task_id='T1', group_id='A', files=frozenset({'src/x.py'}),
                          consumes=frozenset(), produces=frozenset(), advisory_label=None), ...]))
"
```

Each `Task(...)` argument is read directly off one `## Task <N>` heading's fields in the
plan's Execution Queue §7b — `task_id` from the heading number, `group_id`/`files`/
`consumes`/`produces` from that task's `Group`/`Files`/`Consumes`/`Produces` lines.
The labeler is never fed hand-invented arguments: if a task row does not carry the
field, the call cannot be made and the grouping is unvalidated.

If any file-path or signature collisions exist across groups, downgrade affected groups to `Sequential`.

### 1.0 Before Downgrading, Ask Whether The Split Bought The Wait

A `Sequential` downgrade is not free: the waiting group cannot start until the
group it names has finished **and** merged, so every downgrade lengthens the
critical path by a whole group cycle. When the collision that caused it is a
**file two groups both declare**, the wait was bought by how the plan was
split, not by the work.

**Resolve it by giving that file one owning task, not by fusing the tasks that
touch it** — `.agents/rules/sizing-agent-work.md` §3.1 owns this and states
why: fusing is what turns thirty requirements that each touch one settings file
into one thirty-part task nobody can review. Move the file's change into a
single task the others depend on, and the collision, the wait and the monster
all disappear together. Fusing into one `## Task <N>` heading stays available
for the case §3.2 names — two pieces neither of which can be shown to work
without the other — and there it collapses the two groups, and with them a
wait, a review pass and a landing merge.

Run this before finalizing the Execution Queue; exit 0 means no file crosses a
group boundary, exit 1 names every one that does. Either way it first prints
the plan's serial chain and its widest group — the two sizes
`.agents/rules/sizing-agent-work.md` §3.3 judges a split by, and neither of
them changes the exit code:

```bash
python3 .agents/scripts/plan_merge_candidates.py docs/plans/<plan-filename>.md
```

Every flagged file is resolved one of three ways, never left silent, and they
are tried in this order:

- **Give the file one owning task** and make the others `Consumes` its result,
  then re-run. This is the default, and it removes the collision without
  growing any task.
- **Fuse the tasks into one**, only when neither can be shown to work without
  the other (`.agents/rules/sizing-agent-work.md` §3.2). This also collapses
  the two groups, and it is the only case that licenses a bigger task.
- **Keep the split and say why in the plan**, in one sentence beside the
  group, when the tasks genuinely cannot be one — a contract must land and be
  reviewed before its consumer is written, for instance. The wait is then a
  decision on the record rather than an artefact of task sizing.

Measured on one past plan: six files were declared from two or three groups
each, and a single shared client module alone chained three of the plan's
five groups.

This gate reads the plan's own declared `Group` and `Files` lines. A task
heading missing either makes the check raise rather than skip it — a skipped
task would let the gate report success over a plan it never examined.

Note what that downgrade implies for the level below it: because colliding work is
deliberately pulled **into** one group, a group is precisely the set of tasks that share
files. Consecutive implementers inside one group will therefore be handed the same file,
which is what the group notes artifact in `parallel-subagent-driven-development` Step 2
exists to carry.

### 1.1 Critical Path Minimization & Group Decomposition
- **Identify the Critical Path**: Map the dependency graph across groups (via `.agents/scripts/parallel_plan_grouping.py`'s `calculate_critical_path(tasks)`). The sequence of dependent groups with the longest execution depth represents the critical path.
- **De-bloat Blocking Groups**: Never bundle non-blocking tasks (such as test cleanup, peripheral refactors, or post-landing documentation) into a group that gates downstream groups. Non-blocking tasks must be decoupled into independent or trailing groups.
- **Wave 0 Pre-Flight Configuration Bootstrap**: When multiple groups depend on shared configuration (`settings.toml`), environment constants, or shared schema/DTO models, declare a **Wave 0 (Pre-flight)** task that lands directly on the integration branch before group worktrees branch off. This prevents false serialization (e.g. an otherwise independent group being marked `Sequential` purely because an earlier group touched shared settings).
- **Group Velocity & Sizing**: Prefer smaller groups (1–3 focused tasks) for critical-path work. Large monolithic groups (5+ tasks) multiply serialization wait time for all downstream groups.
- **Concurrency Cap Saturation**: Structure independent groups to saturate available concurrency slots up to the configured concurrency cap N (`.agents/config.toml`, `[worktrees] max_concurrent`), queuing additional independent groups in batches of ≤ the configured cap — a queue size, not a wait trigger: a queued batch starts as soon as a worktree slot frees (a merge landing plus the acquire script's release), never only after the whole running batch drains.

### 1.2 A Group Is Also The Review Unit
- **One review pass covers a whole group**, after its last task, with one fix dispatch for all of that pass's findings — execution never reviews tasks one by one.
- **A `Sequential` label may name several groups** (`Sequential (must follow B, C)`), and the waiting group starts only once every one of them has merged.
- **Per-task `Consumes`/`Produces` stay required** because they derive those group labels; they no longer decide anything about review.

### 1.3 Task Granularity & Cohesion (Avoid Micro-Task Splintering)
- **Parallelism is across groups, not within a group**: Tasks within a single group are strictly serial and execute one after another in that group's worktree. Splintering a group's work into multiple micro-tasks (e.g. single-line edits) adds zero concurrency or parallel speedup, but forces multiple separate subagent cold boots and floods the orchestrator context with handbacks.
- **Bundle tightly coupled edits into cohesive functional slices**: Size tasks within a group as cohesive vertical slices (typically 1 to 3 well-scoped tasks per group: e.g. failing test + implementation + contract verification). Each task should represent a complete, test-verified functional unit rather than an artificial fragment.
- **How big one task should be is owned by [sizing-agent-work.md](../../../rules/sizing-agent-work.md) §3, and this file states no threshold of its own**: a file changed by several requirements becomes one owning task the rest consume (§3.1), two pieces fuse only when neither can be shown to work without the other (§3.2), and every task carries a finish line (§3.4). File count decides nothing, and neither does task count — §3.3 judges a split by the longest chain of tasks that must run one after another, which is what actually sets wall-clock.
- **Cohesion is a reason to keep coupled edits together, never a reason to widen a task**: bundling past §3.2's one condition is how a plan grows a task nobody can review, and §10's gate against *too few* task headings does not license it.
- **Maintain Group Independence**: Never merge unrelated work across different files or components into a single group merely to reduce task counts — group boundaries MUST strictly follow file disjointness and interface separation to preserve maximum parallelization across groups.

---

## 2. Thinking Tier Guidance

**A plan never states a model.** Which model a subagent runs on is decided by
[model-assignment.md](../../../rules/model-assignment.md),
which is auto-loaded into every session and is the single owner of that value.
A plan that names a model, a tier of models, or any word standing in for one is
wrong and is fixed by deleting the column, not by reconciling it with the rule.
Two writable stores of one value is a defect the moment it is written, not once
they diverge
([single-source-of-truth.md](../../../rules/single-source-of-truth.md)).

Assign a thinking tier per task group in the Execution Queue:

| Group | Thinking Tier | Rationale |
| --- | --- | --- |
| `<Group ID>` | `standard` \| `ultrathink` | Evidence-backed rationale based on complexity |

### Thinking Tier Rules
- `standard`: The default for every group.
- `ultrathink`: Only for a group whose work is architecture-level — persistence, migration, security, concurrency, or orchestration — and whose failure would be invisible until a real run.
- `ultrathink` raises how long a subagent reasons, never which model it runs on; the two were previously coupled, and that coupling is what let a plan promote implementers to a deeper model.
- A group whose files are prompt, workflow, agent-definition, or documentation text always runs `standard`, per [sizing-agent-work.md](../../../rules/sizing-agent-work.md) §1.

---

## 3. Subagent Execution Handoff

Every `COMPACT`, `STANDARD`, or `ARCHITECTURE` plan MUST be executed by invoking the `parallel-subagent-driven-development` skill ([.agents/skills/parallel-subagent-driven-development/SKILL.md](../../parallel-subagent-driven-development/SKILL.md)).

- The plan-approving lead session NEVER implements code directly in its own session.
- Independent groups run concurrently in dedicated worktrees under `.agents.worktrees/<group-slug>`, the cap N from `.agents/config.toml` (`[worktrees] max_concurrent`) — a plan may define more independent groups than N, but only N run at a time, the rest queuing in batches of ≤ N — a queue size, not a wait trigger: a queued batch starts as soon as a worktree slot frees (a merge landing plus the acquire script's release), never only after the whole running batch drains.
- Sequential groups run step-by-step through the execution skill harness.
- **Inside** a group, tasks run one at a time, each on its own fresh implementer subagent. The group is the concurrency unit; the task is the dispatch unit. Conflating the two is what makes one agent absorb a whole requirement range in a single never-reset context.
- When the plan is ready for implementation, the lead session's final response provides a recommendation to perform context compaction and presents the execution command in a copy-pasteable code block — always carrying all three execution-mode flags, so execution starts without re-asking the autonomy mode:
  ```
  /parallel-subagent-driven-development [REL_PATH_TO_PLAN] --dont-stop --dont-ask --dont-defer [OPTIONAL_ADDITIONAL_INSTRUCTIONS]
  ```
