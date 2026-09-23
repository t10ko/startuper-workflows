Dispatch phase of the parallel-subagent-driven-development workflow: the implementer→reviewer→fix loop this workflow runs inside each group, and every rule binding what a dispatch brief may say (Step 2).

## Step 2: Run this workflow's implementer→reviewer→fix loop per group

Inside each worktree, run this workflow's own sequence: one implementer
subagent per numbered task, dispatched one task at a time within that group;
then one reviewer subagent over that group's work, once, after its last task.
**That is the whole of it — no fix dispatch is issued here.** What the review
finds is admitted to the register and taken by the findings phase
(`landing-and-pr.md` Step 6.5) in one wave after every group has landed, so
this sequence has a last step and cannot circle back to its first. The whole
sequence runs inside that group's single checkout, with exactly one task in
flight per group. Running several groups at once changes only what
surrounds the loop: which groups run at once, and how their results come back
together. When the acceptance gate runs is set below — once per group, after
that group's last task, never once per task. The deep code review is a
different thing entirely and never runs here; it runs once at Step 7.

**No dispatch in this loop passes a `model` argument.** Which model a role runs
on is owned solely by `.agents/rules/model-assignment.md`, which is auto-loaded
into every session. An implementer runs on a standard-capability model,
always, and nothing in this
workflow — no group, no thinking tier, no review round, no retry — may raise it.
Read the model from that rule rather than from a copy kept here.

**Subagent Roles & Tool Scoping: Use dedicated specialists, never `general-purpose`.**
Every implementer dispatch MUST invoke the `sdd-implementer` specialist agent (tools pruned to `Bash, Read, Edit, Write, Glob, Grep`). Every group-level review dispatch MUST invoke the `sdd-reviewer` specialist agent (read-only tools: `Bash, Read, Glob, Grep`).

**`sdd-reviewer` is a completeness gate and nothing else: it answers whether the group's change delivers every acceptance criterion its tasks promised.** It runs no tests, no linters and no type checks, and it makes no quality judgment at all. Both exclusions are structural rather than stylistic. Step 6 runs `ruff`, `pyright` and the touched tests on exactly this group's files at the merge — the same commands, on the merged result, where they also catch what a sibling group broke — and Step 7 then runs the whole suite, so any check run here is run at least twice downstream on strictly better inputs. Every cross-cutting dimension (duplication, typing contracts, security, comments, test design) is consolidated into the one post-landing `code-review-fix-loop` pass. What is left is the question nothing else asks: a suite that passes proves the code that exists works, and proves nothing about code that was promised and never written. Never dispatch untyped `general-purpose` subagents: they inherit full MCP schemas, an unpinned model, and bloated system contexts that drive runaway token consumption.

**Strict 6-Line Handback Contract (Anti-Context-Bloat Invariant).**
To prevent subagent narrative from flooding the orchestrator's context window across multi-hour runs, all dispatched agents MUST return a strict, minimal status card into the conversation:
- `sdd-implementer` returns ONLY:
  ```text
  Status: [SUCCESS | BLOCKED | FAILED]
  Task: [Task <N>]
  Files Changed: [file1.py, file2.py]
  Tests: [N passed in X.XXs]
  Notes: [path/to/group-<slug>-notes.md]
  Not covered: [scope this task did not reach, plus `<count> further findings on <subject>` for anything the five lines above do not carry]
  ```
- `sdd-reviewer` returns ONLY:
  ```text
  Status: [PASSED | FINDINGS]
  Group: [Group <ID>]
  Criteria: [N of M delivered]
  Findings: [None | at most 5 lines, one line each]
  Notes: [path/to/group-<slug>-notes.md]
  Not covered: [criteria it could not settle, plus '<count> further findings on <subject>' for anything over the ceiling]
  ```
All detailed explanations, diff summaries, design choices, fixture notes, and review findings MUST be appended directly to `<plan-workspace>/group-<group-slug>-notes.md` on disk rather than echoed in chat.

**A finding this loop does not fix leaves the diff entirely.** Implementers,
reviewers and fixers all surface problems outside the task at hand — a gap no
task owns, a guard that cannot fire, a spec claim measurement contradicted.
None of it may be written into a code comment, into the plan, or into this
run's state record: it goes in a decision note under `docs/decision-notes/`,
per `.agents/rules/findings-go-in-decision-notes.md`. Dispatch briefs must say
so, because a subagent's report is ephemeral and a finding left only there is
lost the moment the agent ends. The orchestrating session is what carries the
finding from that report to the register, and asks the user before writing it.

Under `--dont-defer` (run-start.md Step 0.1) this deferral path is closed for
findings surfaced inside the run: the finding is entered in the run-state
record's findings register and fixed inside this run, and the final message
reports it in the Findings & Fixes Table. The decision-note rule keeps
governing anything genuinely left unfixed — which, under this flag, the run
never finishes with.

**But not here, and not now.** Step 2 issues no fix dispatch at all. A finding
whose fix lies inside files the task in flight is already editing is folded
into that task; every other admitted finding waits for the findings phase
(`landing-and-pr.md` Step 6.5), which takes them all in one wave once every
group has landed. An orchestrator that dispatches a fix the moment a reviewer
reports one is not being thorough — it is starting the loop this workflow
measured and bounded, where each fix wave raises the findings the next wave
must take.

**A dispatch brief must never ask an implementer to run the whole test suite.**
`.agents/rules/auto-skills.md`'s verification-loop already says the
narrowest relevant check per commit and the project's verify command once at
the end — but
it addresses the agent writing code, not the session writing its brief, and
that gap is where the cost actually lands. A brief that says "run
the unit test suite and report exact counts" makes every task pay a
full suite whatever the rules say, and a brief that also asks for a measured
"baseline" makes it pay two.

The binding standard for every brief this workflow writes:

- **Per commit: nothing beyond the pre-commit gate.** That hook already
  selects only the tests the staged change reaches; it needs no help and must
  not be duplicated by hand.
- **Per task: at most one full-suite run, and only when the change's blast
  radius genuinely warrants it** — a stored-shape change, a widely-imported
  module, a deletion. A narrow change gets its own module's tests and nothing
  more.
- **Never a second run for a baseline.** If a count must be compared, compare
  it to the previous task's recorded number, or state plainly that the
  baseline was not measured. A number nobody can reproduce from a shared
  worktree is worth less than an honest absence — see the run-state guidance
  on concurrent contamination.
- **The project's verify command runs exactly once, at Step 7**, and no brief
  may invoke it.
- **Lint and type-check are not part of this budget.** Ruff, prettier, eslint
  and pyright read the tree without executing it and cost seconds, so a brief
  may ask for them freely and at any point. They also catch what the narrow
  per-commit test selection provably cannot: a reference to a symbol a sibling
  task deleted in the same wave is a type error long before it is a test
  failure, and the selected tests may never import the file that breaks. Never
  trade a linter away to save time, and never take a cheap linter as licence to
  run the full suite.

A brief that departs from this must say why in the brief itself, so the cost
is a decision on the record rather than a habit.

**"One task" means one `## Task <N>` heading in the plan's Execution Queue §7b**,
and the unit dispatched against it is **one fresh implementer subagent per numbered
task** — never one agent carrying a group's whole requirement range. Run
`python3 .agents/scripts/task_brief.py PLAN_FILE N` per task; it writes the brief to
`<plan-workspace>/task-<N>-brief.md`.

**Register before dispatch.** No implementer dispatch is issued before the
orchestrating session has written that task's entry in the in-flight
registry — register-before-dispatch: write the entry, then issue the
dispatch. `run-state.md` owns the registry and its storage shape; the entry
key is the ledger's task key, and the entry clears on harvest — or through
the registry's reconciliation rule, the only other clearing path — so a
task the registry or a completed ledger line names is never dispatched
again while its entry stands. The registry is orchestrator-only state,
exactly like the ledger: no brief ever instructs an implementer to write,
update, or clear its own entry.

**The brief is the complete work order — it resolves what it cites.** Every
identifier the task section names — any requirement, decision, or acceptance
reference the plan or its linked documents define — is reproduced in the brief
in full, verbatim from the document that owns it, so the implementer learns what
its task must satisfy from one read instead of searching for it. Measured
2026-09-12 across 179 implementer runs: 1,106 narrow slice reads and 1,088
repository searches happened in first-60 turns alone, because a brief carried five
requirement numbers and no requirement text. A brief listing anything under
"Unresolved citations" is naming a gap in the plan — fix the plan, and never
instruct the implementer to go find the missing definition itself.

Rule archaeology: design-notes.md §Change 5 and the `ab15c333` regression;
measurement history: design-notes.md §The 1,077-turn runaway-implementer
measurement.

**Never widen a dispatch to batch small same-shape work.** The obvious
temptation is to hand one subagent several tasks when they are the same small
mechanical edit; Change 5's rule wins here, and it never carries a second
task. Batch at *planning* time instead — if several edits belong in
one dispatch, they belong in one `## Task <N>` heading, decided in the plan where a
human can see it, not widened by an orchestrator mid-run. This binds the
dispatch unit and nothing else: the reviewer construction rules, the ledger
format, and the fix-loop rounds are untouched by it.

**Two different things are called "review" in this repository, and confusing them is expensive.** The per-group pass described immediately below is an *acceptance gate*: one `sdd-reviewer` dispatch that checks whether that group's tasks met the acceptance criteria the plan already wrote down, and whether its declared tests pass. It is not a code review. The *code review* — the deep, cross-cutting quality pass — is the `code-review-fix-loop` skill, and that one runs **exactly once per run, at Step 7, over the whole combined diff, never per task and never per group**. Nothing in Step 2 may dispatch `code-review-fix-loop`, for any reason.

**One acceptance gate per group, after that group's last task — no per-task gates.**
A group is the unit of parallelism and the unit of landing: its tasks run one at a
time inside one worktree, the whole group lands as a single merge of its branch
into the integration branch (Step 6), and a
group that follows it does not start until that merge reads `Merged` (Step 3). So
nothing outside a group can ever be built on that group's unreviewed work, whatever
the shape of the dependency between them. Reviewing tasks individually buys no
protection against that; it only multiplies the review count by the task count.

The pass is a task review widened over the whole group, not a new review kind: its
review package spans the group's first task's BASE to its last task's HEAD, its brief
carries every task's `## Task <N>` requirements, and its findings go to the register
for the findings phase to take. The reviewer is handed exactly three inputs and never
more — the brief, the report file, and the `python3 .agents/scripts/review_package.py`
diff file.

**The brief hands the gate its evidence, so the gate does not rebuild it.**
Measured 2026-09-21 on one live acceptance review: 1,008 commands over 3h57m,
about 14 seconds apiece, almost all of it re-deriving facts the group's own
implementers had already established and written down. Every acceptance brief
MUST therefore carry, in the brief itself: each task's acceptance criteria
verbatim, the group notes path the implementers wrote as they went, the tests
each implementer reported passing, and the review-package diff path. The gate
reads the diff and opens a source file only where the diff alone cannot settle
whether one named criterion is delivered — it is not re-establishing what the
group did, it is walking a checklist against a diff it was handed.

**A brief that lists no acceptance criteria has nothing for the gate to
check.** The criteria come from the plan's own `## Task <N>` sections, so an
empty list is a defect in the plan, not a group that passes by default: fix
the plan before dispatching the gate, exactly as an unresolved citation is
fixed rather than delegated.

**The accepted cost, stated:** a defect in an early task of a group is found at that
group's review rather than immediately, so later tasks in the same group may need
rework in that one fix round. Nothing unreviewed ever merges and no other group is
ever exposed — what this trades is rework size, not correctness. Measured across four
real plans, a 59-task plan drops from 59 review passes to 7, and a 41-task plan from
41 to 7.

**This rule holds only while dependencies are group-to-group.** `label_groups()`
merges every task's files and `Consumes`/`Produces` into one set per group before
comparing anything, so a task-level cross-group wait cannot be expressed and no
consumer can start early. If that ever changes, a consumer could begin against
unreviewed work and per-task reviews would be needed again — the two decisions move
together or not at all.

Four rules shape this loop, and they are the complete list of places it departs
from a plain one-implementer-one-review default: model selection is bound to
the standard-capability floor for implementers, a dispatch never carries a
second task, review runs
once per group rather than once per task, and there is no whole-branch review
step at all — Step 7's single integration `code-review-fix-loop` pass is the
only review above task level.

**Carry file-shaping context forward on disk, never in a dispatch prompt.** Because
`label_groups()` pulls file-colliding tasks *into* one group by construction,
consecutive implementers in a group are routinely handed the same file. Each group's
worktree therefore holds one `<plan-workspace>/group-<group-slug>-notes.md`
(Step 1 item 4 defines `<plan-workspace>`; it sits beside that group's ledger).
Seed it, before that group's first dispatch, with the group's block from the plan's
Execution Queue §7c — the planning-time half of the same artifact.
Every implementer appends the fixture, helper, import, and file-layout decisions it
made; every later dispatch in that group receives the path with an instruction to read
it first. **Never paste accumulated prior-task history into a dispatch prompt** —
this is a file handoff precisely so the
context lands in the reader that needs it rather than resident in the orchestrator's
own context for the rest of the run.

Never let an implementer or reviewer subagent this inner loop dispatches
touch a `.py` file without an explicit instruction to read
`.agents/rules/python-antipatterns.md` and `.agents/rules/clean-typing.md`
first. Do not assume either file reaches that subagent by ambient auto-load.
`.claude/rules` projects both behind a `paths: ["**/*.py"]` key, so at best
they arrive only once that subagent has itself read a Python file — which
never happens when its first Python action is writing a new module, and may
not happen at all, since `.agents/workflows/detailed-plan.md` records that
dispatched agents can carry no ambient `.claude/rules` payload. The
subagent cannot check which case it is in, so the instruction stays
unconditional. Put it in the dispatch prompt itself, every time, the same way
the no-model-argument sentence above is.

Before dispatching any implementer, read the plan's `Grounding:` header
field for the grounding artifact path. Do not derive it from the spec slug —
the slug can differ when a spec was split from another. If the field is
present and the file exists, every implementer dispatch MUST include its
path with the instruction to read it first — it carries the file inventory,
symbol map, and excerpts the scout already used, so the implementer does not
re-derive codebase context from scratch. The implementer still reads source,
but only to verify the specific claim its task changes — not to rebuild a
model that already exists. If the `Grounding:` field is absent or `none`
(no linked spec, no grounding artifact, or a plan that predates the
convention), proceed without it. Put the path in the dispatch prompt itself,
every time, the same way the python-antipatterns instruction above is.

**Every dispatch brief states the unfiltered-read budget.** Measured across
1,060 subagent runs: shell file-peeking returned 60% of everything commands put into
agent context, and a peeked line is re-read on every later turn of that agent, so one
wide read is paid many times over. The repo's read budget is 120 lines per
unfiltered read and `.agents/hooks/block_large_file_dump.py` enforces it, but a
subagent that meets the block for the first time mid-task pays a wasted turn learning
it — so say it up front, the same way the python-antipatterns instruction above is:
read the range the task needs, and send anything larger through a filter or into a
file under this task's own scratch root rather than into context. The hook fails open
on a glob, a variable, a missing file, or a command it cannot parse, so the brief is
what covers those, not the hook.

**The same brief states the search discipline, because search — not file
reading — is the larger channel.** Measured 2026-09-21 across one run's 15,445
shell calls, which returned 26.6 MB into subagent context: `rg` alone returned
9.3 MB over 5,771 calls and `sed` 6.7 MB over 2,232, and 28% of all those bytes
came from commands carrying no output limiter at all — no pipe to a filter, no
redirect to a file. None of that is caught by the unfiltered-read hook, which
sees a file-dump shape and not a search that happens to match a thousand lines.
Every brief therefore states, in the brief itself:

- **Ask a search the narrowest question that answers it.** `rg -c` when the
  answer is how many, `rg -l` when the answer is which files, `rg -o` when the
  answer is the matched text — a full matching line is what you ask for when
  the surrounding line is what you actually need.
- **A command whose output you cannot predict gets a limiter in the same
  breath** — a pipe to `head`, `wc`, or another filter, or a redirect to a file
  under this task's scratch root. Predicting wrong is the common case, which is
  why the limiter goes on before the first run rather than after a surprise.
- **Never re-issue a call you already made in this session.** Measured on the
  same runs: 587 calls were an exact repeat of one the same agent had already
  issued, re-delivering 4.2 MB. The result of the first call is still in your
  context — re-reading a file to check whether it changed is only meaningful
  after you or a tool has changed it.

Each of these states how to ask a narrower question. None of them bounds what a
subagent may learn, and no brief may restate them as though it did.

**Every dispatch prompt names a scratch root unique to its task.** A dispatched
task's scratch outputs — logs, temp files, throwaway scripts, reproduction
dumps — never sit at a fixed path another task could also write. Two tasks
that both write `logs/<plan>.log`, or any shared tmp file, overwrite each
other silently: whichever finishes second wins, and the first task's evidence
is gone with nothing to notice. Prevention is by convention once this rule
lands, not by mechanism — no guard or hook checks it, so a brief that hands
an implementer a bare fixed scratch path defeats it on its own. Derive the
path from the identity the brief already carries: `<plan-slug>/task-<N>/`
inside one of the git-ignored scratch homes — e.g.
`logs/<plan-slug>/task-<N>/repro.log` or `verify/<plan-slug>/task-<N>/probe.py`
— never a new top-level directory beside them, with the run's branch added as
one more component when the path sits outside the worktree. The homes stay exactly where the repo's conventions fix them — `logs/` for
ad-hoc command
output, `verify/` for sandbox scripts; only the namespacing is new, and it
lives inside them. The ledger and the group-notes artifact are not scratch:
Step 1 item 4 already namespaces those per worktree and plan workspace.

When Step 0.1 fixed the run with `--dont-stop`/`--dont-ask` (or the question
selected "Proceed without stopping or asking questions"), every implementer
dispatch prompt MUST explicitly instruct the subagent to operate
autonomously: resolve technical decisions using best engineering judgment without
pausing for conversational questions, record decisions in
`<plan-workspace>/group-<group-slug>-notes.md`, and strongly lean towards covering and
fixing all discovered gaps and edge cases encountered in its task area rather than
skipping or leaving them unaddressed (unless an encountered gap is so massive that it
warrants a separate standalone plan — an escape hatch that exists only when
`--dont-defer` is absent).

When `--dont-defer` is active, every dispatch prompt MUST instead instruct the
subagent to fix every gap, edge case, or defect it finds in its task area
within this run — folding it into the current task's work when adjacent,
reporting it for a dedicated fix dispatch when it is not — and to name each
fix in its handback's `Notes` line so the orchestrator can register it in the
run-state record's findings register. The massive-gap exception does not
exist under this flag.

That instruction reaches only what the **admission gate** (`run-start.md`
Step 0.1) admits, and every dispatch prompt MUST carry the gate's own test
rather than the flag alone: report something wrong **now**, refuse a finding
whose harm is conditioned on an event that has not happened, refuse one the
subagent's own text places outside what this run changes, and never report
the plan, spec, or grounding documents as defective while the run executes.
A reported finding MUST carry the file and line that establish it and the
command or reading that confirmed it, because the fix dispatch that receives
it is charged for every re-derivation the report leaves it to repeat.


