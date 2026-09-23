# Sizing Agent Work

Recorded 2026-09-11 at the user's direction, after measuring 53,622 real turns:
98.29% of every token billed was re-reading context the agent had already seen,
and the read-to-write ratio was 415:1. A turn is billed the full depth of its
context, so context depth — not dispatch count — is what work costs.

## 1. Route by the dominant work kind, per group — not per plan

`detailed-plan`'s `WORKFLOW_DOCS` profile is all-or-nothing: any production `.py`
file disqualifies a plan from it. That test mis-routed a change that was 71%
prompt and workflow text into `ARCHITECTURE`, the heaviest route, on the strength
of two source files totalling 10,571 bytes.

**A plan states one profile; each of its groups states its own work kind.** A
group whose `Files` are prompt, workflow, agent-definition, or documentation text
runs at the standard thinking tier with no `ultrathink`, whatever the plan's profile
is. Only a group changing executable behavior inherits the plan's tier.

## 2. A file move is a shell command, never a model rewriting text

Relocating text verbatim — splitting a file, moving a section, renaming across a
tree — is `sed`/`git mv` work. A model doing it must emit every token at output
prices and then re-read the growing result on every later turn; one measured case
put 125,625 bytes (~31,400 tokens) of pure retyping into a plan.

Extract, delete, then prove nothing was lost by byte count:

```bash
sed -n '<start>,<end>p' "$F" > references/<topic>.md
sed -i '' '<start>,<end>d' "$F"
git show HEAD:"$F" | wc -c            # must equal the parts, plus only new pointers
```

A task whose work is relocation states the commands in the plan. A plan that asks
an implementer to "move text verbatim" without them is authoring a retyping job.

## 3. Cut tasks along file ownership, and merge only what cannot be verified apart

Revised 2026-09-22 at the user's direction. This section used to size a task by
**turns of real work** — merge under ~13, split at or above. That number was
never usable: a planner cannot observe a turn count at the moment it has to
decide, and the measurement proves nobody ever did. Across one run's 52
subagents the mean agent ran **448 turns**, 34× the threshold, with nothing
noticing, because there was nothing to notice with. A rule that can only be
evaluated after the work it was supposed to shape is not a rule.

What a planner *can* observe is what the plan already records: which files each
piece of work changes, and which contracts it consumes and produces. Those
fields decide both questions below.

### 3.1 One file, one owning task

**When several requirements all need the same file changed, that file's change
is one task, and every other task consumes its result rather than editing it
too.** This is the whole of the splitting procedure, and it is what keeps a
plan parallel.

A file declared by many tasks is the plan's critical path, because
`.agents/scripts/parallel_plan_grouping.py` puts colliding tasks in one group and a
group's tasks run one at a time in one checkout. Measured on one real plan:
six files
were declared from two or three groups each, and one shared client module
alone chained groups 1, 2 and 5 into a
serial run. `python3 .agents/scripts/plan_merge_candidates.py <plan>` names every
such file and the tasks that own it; run it before finalizing the Execution
Queue, and treat each line as a question about how the work was cut.

**Answer that question by moving the work, not by fusing the tasks.** Fusing is
what produces a task nobody can review and one agent cannot finish: thirty
requirements that each touch one settings file become one thirty-part task.
Give the file a single owning task, let the rest depend on it, and both the
monster and the serial chain disappear together.

### 3.2 Merge only what cannot be verified apart

**Two pieces of work are one task when neither can be shown to work without the
other, and for no other reason.** The clearest case is a failing test and the
change that turns it green — split across two tasks, the first commits a red
suite. The plan template already forces that pair.

**Do not merge to save rediscovery.** That was the old threshold's reasoning
and the repo already solved it another way: consecutive implementers in a group
share `group-<group-slug>-notes.md`, where each one appends the fixture, helper,
import and layout decisions it made, and the next one reads it before starting.
A second task in the same group therefore begins informed *and* shallow, which
is the combination a merged task can never have.

- **Same file, different tasks is normal.** Grouping already puts them in one
  worktree, one at a time, so nothing collides.
- **One edit repeated across many files is one task** — a paragraph appended to
  twenty agent definitions, six near-identical prompt files. Its context is one
  decision applied N times, and N agents would each rebuild that decision.
- **File count still decides nothing.** A one-line edit across eight files is
  one task; a single-file contract rewrite may be three.

### 3.3 Judge a split by its longest serial chain, never by its task count

More tasks spread across more groups finish sooner; more tasks inside one group
do not. Before finalizing, ask which group holds the most tasks and which file
put them there — that pair is the plan's wall-clock floor, and it is the only
size worth optimizing. A plan with twice the tasks and half the chain is
strictly better, and the task count alone would have called it worse.

`python3 .agents/scripts/plan_merge_candidates.py <plan>` prints both numbers
before anything else, so this is measured rather than eyeballed: the heaviest
chain of dependent groups weighted by the tasks each holds, and the widest
group with its share of the total. Neither number has a threshold and neither
sets the exit code — a threshold is what §3 just retired, and inventing a new
one here would repeat it. They are the two sizes to look at and argue about.

### 3.4 Each task states how it is finished

A task is dispatchable only when it carries its own finish line, in one of
exactly two shapes: **a runnable check** written out as a command, failing now
and passing when the work is done; or **a closed list** enumerated in the plan
that cannot grow once dispatched. Work that is neither is an investigation —
it reports findings and changes nothing.

This is a validity test on the cut 3.1 and 3.2 produce, not a second way to
make it. It exists because the three most expensive agents ever measured here —
1,893, 1,757 and 1,002 turns — were each handed work with no condition that
could tell them they were done, and two of them were handed lists that grew
while they worked.

## 4. A dispatch round trip is capped

Measured: each agent dispatch left 4,140 tokens permanently in the orchestrator's
context — the brief sent out plus the report coming back — against Anthropic's
published guidance of 1,000–2,000 tokens for a returned summary, and against this
repo's own five-line card. Together those round trips were 31.5% of everything
filling a long session.

- **A brief goes out by path.** Write it to the plan workspace and send the path.
- **A report comes back as the five-line card and nothing else.** Detail goes to
  the group notes file on disk.
- **Neither cap ever shrinks the reading.** They bound what re-enters the
  orchestrator, never what the subagent inspects.
