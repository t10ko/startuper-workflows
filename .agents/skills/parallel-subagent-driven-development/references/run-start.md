Run-start phase of the parallel-subagent-driven-development workflow: everything from checking for a prior interrupted run through creating each group's worktree and ledger (Steps 0, 0.1, 0.5 and 1).

A run follows the workflow text as of its start; a later change to the text binds an already-running run only when the owner says so in the session.

## Step 0: Check for a prior interrupted run

Before creating anything, check for three things left behind by an earlier,
interrupted invocation of this workflow:

- Pre-existing worktrees at `.agents.worktrees/<group-slug>`.
- A legacy run-state file at `docs/runs/parallel-run-state.md` — kept
  indefinitely as a live artifact for any run that predates this workflow's
  branch/commit/push/PR model — whose run is not marked finished.
- Any run-scoped state record under `docs/runs/plan-runs/` (see
  [Run-state artifact](#run-state-artifact) below), read via
  `agentic_workflows.plan_run_state.parse_plan_run_state`, whose `Run status` field
  is not `Finished`. This directory is also checked indefinitely — never
  assume it's empty just because no run is currently active.

If any of these is found:

- The two nested checks below apply only when a run-scoped state record
  under `docs/runs/plan-runs/` exists — the legacy
  `parallel-run-state.md` file predates PR tracking entirely and has no `PR
  URL` or `Terminal outcome` fields to check. If only a legacy file (or only
  a pre-existing worktree with no record at all) is found, skip straight to
  the resume/discard choice below.
- If the record names an open PR, call `get_pull_request_state` (from
  `agentic_workflows.github_client` — full contract at
  `.agents/rules/github-pr-api.md`) before offering resume at all. Offer
  **resume** only when that call returns exactly `"OPEN"`; any other value
  (`MERGED`, `CLOSED`, or an unrecognized value) means resume is unsafe —
  report the actual returned state to the human and offer only
  discard-and-clean.
- If the record's `Terminal outcome` field already names a recorded failure
  from a prior attempt, surface it as a blocking gate: report it to the
  human before any new work proceeds, and require an explicit decision
  (resume past it, or discard) rather than silently retrying. A recorded
  success in that field is informational only — it never blocks anything.
- Stop and ask the human to choose explicitly between:
  1. **Resume** — reattach to the existing worktrees and ledgers, read each
     group's last recorded state from the run-state record and from
     `<plan-workspace>/progress.md` inside each worktree (see Step 1 item 4 for
     how that directory resolves — it is never the flat
     `docs/runs/progress.md`), and continue from there.
  2. **Discard and clean** — remove the stale worktrees and branches. Every
     worktree this workflow creates lives at `.agents.worktrees/<group-slug>`,
     the agent-owned root, so `git worktree remove --force <absolute path>`
     (and, for its `sdd/`/`plan/` branch, `git branch -D`) is now the
     prescribed way to clear one, uncommitted changes included — there is
     no longer a separate escalation path for a stale worktree with
     uncommitted changes worth keeping; discard means discard, and the
     human's explicit discard decision is what satisfies the durability
     question here (the script's `release` path is durability-gated — a
     dirty tree is committed to its branch first, never discarded; discard
     by force is exactly the human overriding that for work they
     have ruled expendable). Use the
     worktree's absolute path, per the mechanical requirements above — a
     relative one resolves against wherever this discard step happens to
     run from, not against the worktree's own location.

Never resume or discard silently. This is the same rule as every other halt
point in this workflow: agents propose, humans approve.

## Step 0.1: Execution-mode flags & the autonomy gate

The run's execution mode is fixed before implementation starts — immediately
after Step 0 interrupted-run check clears and before creating branches,
worktrees, or dispatching tasks in Step 0.5/Step 1 — either by three flags on
the invoking command or, when none is given, by asking the user exactly ONE
question using `AskUserQuestion`.

### The three flags

- **`--dont-stop` — the Continuous Non-Stop Execution Invariant.** The agent
  MUST NEVER stop or pause execution mid-flight to ask conversational
  questions, request check-ins, or solicit continuation approval. Execution
  proceeds continuously through all remaining workflow steps (Steps 0.5
  through 10) until the entire approved plan, all task groups, integration
  review, the project's verify command, commit, secret scan, and PR creation
  are completed.
- **`--dont-ask` — the Autonomous Best-Judgment Decision Rule & Mandatory
  Disk Documentation.** The agent resolves every design nuance, contract
  ambiguity, or implementation choice autonomously — never pausing to ask —
  by selecting the "best version" / highest-integrity architectural solution
  based on its best engineering judgment (strictly adhering to project
  invariants: root-cause fixes over symptom patches, clean typing, MVP
  contracts, and zero shims). Every single autonomous decision, choice, or
  tradeoff MUST be explicitly documented on disk in the run-state narrative
  (`docs/runs/plan-runs/<branch>.md`), group notes
  (`group-<group-slug>-notes.md`), and the final PR description, and the run
  renders the End-of-Run Plain-Language Decisions Table (below).
- **`--dont-defer` — the Zero-Deferral Gate.** The agent addresses everything
  the admission gate below admits, and defers none of it. Every admitted
  finding — an implementer's discovered gap, a reviewer's finding, a fixer's
  or the integration review's discovery, whether or not the plan's original
  scope owned it — is fixed inside this run, at exactly one of two moments.
  **Adjacent**, when the fix lies inside files the task in flight is already
  editing: it is folded into that task, because a fix in a file already open
  costs nothing to carry. **Otherwise it waits for the findings phase**
  (`landing-and-pr.md` Step 6.5), which takes every remaining admitted finding
  in a single wave after all groups have landed, and which is the only place
  this workflow issues a dedicated fix dispatch. No finding is fixed the
  moment it is raised, and no fix dispatch is issued mid-run, because a repair
  that runs the instant a finding appears feeds the run's own output back into
  its own input with nothing deciding when that stops. The Strong
  Bias's "separate, standalone project/plan" exception and the
  decision-note deferral path (`dispatch-and-briefs.md` Step 2) do not exist
  under this flag: a gap found during the run is fixed during the run,
  whatever its size, and the Findings & Fixes Table at the end tells the
  user it was taken. The orchestrating session keeps a **findings register**
  in the run-state record's narrative — one entry per finding: where found,
  by which role, what it was, the fix, and where it landed — and a finding
  is closed only when its fix is committed, so the run never finishes with an
  open register. An admitted finding that needs a decision is decided, fixed,
  and listed in the Decisions Table — the register has no question status.

- **The admission gate — what counts as a finding the run must fix.** The
  Zero-Deferral Gate decides that an admitted finding is fixed in-run; it
  never decided what is admitted, and this is that decision. A finding is
  admitted when its own text establishes that something is wrong **now** —
  code that misbehaves today, a check that cannot fire, a test that passes
  while proving nothing, a contract two producers already disagree about.
  Three classes are refused at detection. Refusing one is not deferral:
  nothing enters the register, so nothing is left open.

  1. **Its harm is conditioned on something that has not happened.** When the
     finding's own text makes the damage depend on a future or hypothetical
     event, it states a risk, not a defect. The test is whether removing the
     conditional leaves anything wrong today — not whether the sentence
     matches some remembered phrasing, because the phrasings vary and no list
     of them is the test. Code paths that already disagree count as wrong
     today even when no data reaches them — the disagreement is the defect,
     not the data that would expose it. Measured 2026-09-21 across the two
     runs then in flight: seven register entries read this way, and every one
     that reached a disposition closed with no change made.
  2. **It is outside what this run touches, by its own admission.** A finding
     that names material this run does not change is a finding about the
     repository, not about this run's work, and the run is not where it gets
     decided. The admission unit for "material this run does not change" is
     the file: a finding in a file the run changed is inside the run, whatever
     symbol, line, or subsystem its text names.
  3. **It is about the run's own planning documents.** `docs/plans/`,
     `docs/specs/` and their grounding files are not review targets while the
     run executes: they describe work that is still moving, so every landed
     task can make them stale again, and a run that chases that spends
     dispatches proofreading its own paperwork. Measured on the 2026-09-20
     stall-timeout run: seven dispatches existed only to reconcile the plan
     document with itself, and 36 register entries named one of them as the
     fix. Reconciling those documents belongs to the close-out
     (`landing-and-pr.md` Step 12), once nothing further will move them. This
     refuses the *documents* — a defect they merely describe is admitted on
     its own evidence like anything else.

  **An admitted finding carries its own evidence**: the file and line that
  establish it, and the command or reading that confirmed it. A fixer handed
  that evidence does not re-derive it, and re-derivation is where a fix
  dispatch's measured cost actually goes — across those same two runs the
  subagents spent 15,445 shell calls and 5,948 file reads, and every byte
  returned was re-sent on every later turn of the agent that asked for it.

  **A refused finding is never silently dropped.** It is stated in the run's
  final report to the user, which is
  `.agents/rules/findings-go-in-decision-notes.md`'s own instruction for a
  finding whose decision-note approval is not available in the moment; under
  `--dont-defer` the same file authorizes that run's one decision-note
  register, written at run end, for exactly these refused-and-reported
  findings.

Any flag present: the question below is **skipped** — each named flag fixes
its axis for the whole run, and each unflagged axis runs this workflow's
standard default (its normal pause/ask/escalate paths, and the decision-note
deferral rule for findings). This is what lets a run started from
`detailed-plan.md`'s recommended command begin without re-asking how to
execute. No flag present: ask the question. Either way, record the resolved
mode in the run-state record's narrative at Step 0.5, so a resumed or
compacted session restores the mode instead of re-deriving it.

**Hard invariants no flag ever overrides.** The flags move judgment calls
from the human to the agent; they never waive a safety gate. Under every
combination: the secret-scan hard-stop (Step 9 of `landing-and-pr.md`) still
halts for the human; the consent gates (`.agents/rules/memory-consent.md`)
still gate their writes — the flags authorize none; the project's verify
command and the per-merge scoped checks must
genuinely pass — a red gate is fixed, never waived; the durability
invariant, the acquire-script worktree lifecycle, the git deny-list, and cap
N stand unchanged; Step 0's interrupted-run resume/discard choice stays the
human's call (it concerns a prior run's work, not this run's mode); and a
genuinely hard unresolvable blocker (fatal toolchain failure, an
irreconcilable merge conflict after bounded resolution) still halts a
`--dont-stop` run. One boundary qualifies the red-gate rule: when a red gate
is main's own — failing on commits main already has, not on this run's diff —
the run reports it and merges main only to the last green commit, or fixes it
in a separate commit on main. A red gate in this run's own diff is still
fixed, never waived.

### The question (no flags given)

- **Question header / prompt:** `Execution Autonomy & Questioning Mode`
- **Question text:** `Should the agent proceed autonomously without asking conversational questions (autonomously selecting the best solution using its best judgment, covering discovered gaps, and documenting every decision on disk), or should it pause to ask conversational questions as ambiguities or checkpoints arise?`
- **Options (symmetric, recommended first):**
  1. `Proceed without stopping or asking questions (Recommended) — Runs both the --dont-stop and --dont-ask invariants above, plus the Strong Bias Towards Covering Discovered Gaps below. It is not the Zero-Deferral Gate.`
  2. `Ask conversational questions — Pause and ask questions whenever non-trivial design ambiguities, checkpoints, or scope choices arise; findings defer under the decision-note rule.`

### Strong Bias Towards Covering Discovered Gaps (question-option 1 only; superseded by `--dont-defer`)

When encountering additional work, unhandled edge cases, missing test coverage,
or adjacent defects/gaps during implementation, the agent MUST be
strongly biased towards covering and resolving all gaps it finds in the same
execution run. **Exception:** ONLY when a newly discovered gap is so massive,
architecturally disjoint, or expansive that resolving it genuinely warrants
being handled as a separate, standalone project/plan. If the gap is adjacent
to touched code, in the same pipeline/subsystem, or necessary for
end-to-end correctness, the agent MUST fix and cover it immediately rather
than skipping, deferring, or leaving it behind. Document every covered gap
and rationale on disk.

### End-of-Run Plain-Language Decisions Table

Any run that executed with `--dont-ask`, with `--dont-stop`, or on
question-option 1 MUST, at the very conclusion of the workflow (in the final
user-facing message upon completing Step 10/Step 11), present a dedicated
Markdown table of decisions made throughout the run. Every decision in this
table MUST be described in a very easy, plain-language manner suitable for a
non-technical creator, explaining the situation faced, what was decided, and
why, without cryptic jargon or internal identifiers. Use clear columns (e.g.
`Decision / Problem Encountered`, `Choice Made`, `Why / Impact`) so the user
can review all autonomous choices at a glance.

### If the answer is "Ask conversational questions"

The agent follows standard HITL behavior: pause and surface questions to the
user whenever non-trivial ambiguity, design alternatives outside the approved
plan, or scope expansions arise, and findings defer under the decision-note
rule (`dispatch-and-briefs.md` Step 2).

## Step 0.5: Create the run's branch and state record

1. `git fetch origin main` — always branch from the fetched remote tip, never
   from whatever happens to be checked out locally.
2. Pick a branch name (e.g. `plan/<slug>`, derived from the plan's own slug)
   and confirm it collides with neither an existing local/remote branch nor
   the `sdd/<group-slug>` convention already used for per-group branches —
   on a collision, halt and report it to the human rather
   than silently reusing or overwriting it. `plan/` and `sdd/` are not just
   naming examples here: they are the exact two prefixes
   `.agents/rules/agent-worktrees.md`'s `git branch -D` carve-out checks —
   the only branches this workflow may ever force-delete. Under the current
   lifecycle the run's group branches are in fact **retained** after their
   worktrees are released (Step 6), so a post-verify attribution fix can
   re-create a worktree from the branch; the carve-out exists for the
   explicit discard path (Step 0) and human-directed cleanup.
3. `git branch <name> origin/main` — create the run's own branch off that
   fetched tip.
4. Create the run's state record via `write_plan_run_state` (from
   `agentic_workflows.plan_run_state`) at `record_path_for_branch(<name>)`, with
   `Run status: InProgress`, the branch name in the `Branch` field, and the
   integration worktree's path already in the `Integration worktree` field —
   a single write, since both are already known by this point
   (`<main-checkout-absolute-path>/.agents.worktrees/<run-slug>`). **This
   record must be written before the worktree is acquired** (item 5): the
   acquire script derives its cap-count exemption for the run's integration
   worktree from exactly this record, and a missing record exempts nothing —
   the worktree would count against N (fail safe). See
   [Run-state artifact](#run-state-artifact) in `run-state.md` for the full
   seven-field header this record carries. `update_plan_run_state` is never
   used for this initial creation — only for the later field updates in
   Steps 6-11.
5. Record the run's BASE in the state record's free-form narrative:
   `git rev-parse <name>` right after item 3 — the integration branch's
   pre-run state. The Step 7 `code-review-fix-loop` dispatch reads this
   value as its diff baseline (`git diff BASE`), so it covers exactly this
   run's work and nothing that lands after the loop starts.
6. Acquire the integration worktree by running
   `python3 .agents/scripts/worktree_acquire.py acquire --name <run-slug> --branch <name> --run <name>`
   — never a raw `git worktree add` command, which is prohibited to agents
   by `.agents/rules/agent-worktrees.md` (backed by a Claude Code hook). The
   `--run <name>` is this run's own branch: the per-run cap counts only
   worktrees leased to it. The script prints the worktree path on stdout
   (exit 0), refuses with actionable stderr (exit 1 — your run's N slots
   are in use; stderr names your run's holders and the next actions: land
   or release one of them), or fails closed on undecidable input (exit 2 —
   halt, report to the human). The integration worktree is exempt from the
   count via the record item 4 wrote; every other slot N
   belongs to groups and review-fix batches. Never a tool that picks its own
   directory or writes to `.claude/worktrees/agent-<hex>/`, a location this
   repo does not treat as agent-owned.

There is no main-checkout-cleanliness gate here — unlike the old model, this
workflow never lands anything on the main checkout's own working tree, so a
dirty main checkout has nothing left to leak into. All landing and review
now happen inside the integration worktree created above (see Steps 6/7).

### Wave 0 Bootstrap Tasks (Pre-flight Configuration & Shared Schemas)
If the plan defines Wave 0 / bootstrap tasks (e.g. shared configuration
additions, environment constants, or shared schema/DTO models), execute and
commit those tasks directly in the integration worktree before creating any
group worktrees. Once committed on the integration branch, subsequent group worktrees will automatically branch off this shared foundation without false serialization or merge conflicts.

## Step 1: Create one worktree and ledger per group, as each becomes eligible

### Single-Group & Linear Sequential Chain Fast Path (1 Worktree)

When the plan decomposes into **exactly one task group** or a **purely linear sequential chain** of groups (where every subsequent group is `Sequential (must follow <group>)` with no concurrent sibling groups):
- **Consolidated worktree:** Step 0.5 and Step 1 are unified. The integration worktree acquired at `<main-checkout-absolute-path>/.agents.worktrees/<run-slug>` also serves directly as the execution worktree for all groups in the linear chain.
- **No secondary checkout:** Skip acquiring secondary worktrees or creating separate group branches. The groups execute serially, directly within the integration worktree on the run's branch.
- **No duplicate bootstrap:** Skip duplicate dependency-bootstrap runs for each group.
- **Workspace & ledger:** Resolve `<plan-workspace>` directly in this integration worktree via `python3 .agents/scripts/sdd_workspace.py PLAN_FILE`. The ledger is `<plan-workspace>/progress.md`.
- **Fast-path landing (Step 6):** Landing is a direct no-op. Tasks commit straight to the run's own branch — which IS the integration branch — so each group's completed work is already on the integration branch; there is no separate merge to perform. Each group runs its tasks, completes `sdd-reviewer` acceptance, and commits or progresses in-place before the next sequential group starts.

### Multi-Group Concurrent Worktree Fan-Out (2+ Concurrent Groups)

**Rollout gate.** Before the first group acquire of the run, run
`python3 .agents/scripts/worktree_acquire.py status --run <branch>` and read
this run's count. The cap's enforcement is treated as live only when the
calling run's own worktree count (its integration worktree exempt) is <= N;
other runs' worktrees are irrelevant to that count and never appear in it. A
count above N means this run's own holders are over cap: reclaim its stale
holders via `release --name <slug> --run <branch>` (durability-gated — the
script commits uncommitted work to the holder's branch first), or
land or release a live holder before fanning out. Do not delete other runs'
worktrees yourself to make room — they never count against this run. Once
`status --run <branch>` reports a count <= N, enforcement is live and the
fan-out proceeds.

When the plan decomposes into 2 or more groups, every group needs a worktree eventually, but not all at the same moment:

- An `Independent (parallel-safe)` group is eligible for a worktree
  immediately.
- A `Sequential (must follow <group>)` group's worktree acquisition — not
  only its task dispatch — must wait until `dependency_wait_satisfied()` (Step 3)
  is `True` for its declared dependency. Only then acquire its worktree off
  the integration branch's now-current tip, since the dependency's merge has
  just landed on it (Step 6). Acquiring a Sequential group's worktree early,
  off a stale tip, would silently drop the dependency's own changes from that
  group's view.

For each group in a multi-group plan as it becomes eligible:

1. Run
   `python3 .agents/scripts/worktree_acquire.py acquire --name <group-slug> --branch sdd/<group-slug> --run <name>`
   — never a raw `git worktree add` command (prohibited to agents by
   `.agents/rules/agent-worktrees.md`; never a tool that writes to
   `.claude/worktrees/agent-<hex>/`, a location this repo does not treat as
   agent-owned). `--run <name>` is this run's own branch from Step 0.5: the
   cap counts only this run's leases, so another run's worktrees never
   block a group and are never touched. The script creates one dedicated
   worktree and branch per
   group at `<main-checkout-absolute-path>/.agents.worktrees/<group-slug>`,
   branching from the run's own branch created in Step 0.5 — never from
   whatever happens to be checked out in the main working tree (or, for a
   `Sequential` group, from the integration branch's current tip at the
   moment it becomes eligible) — the run's own branch is the integration
   branch for this run; there is no separate branch to create for it. The
   script reuses an available existing worktree when one fits, refuses when
   the run's N slots are in use (exit 1 — not a halt: the group waits for a
   slot, which an earlier group's Step 6 release frees automatically), and
   fails closed on undecidable input (exit 2 — a halt trigger, item 3).
2. **Never bootstrap a new worktree with an auto-detected package manager.**
   An auto-detect runs whatever installer it guessed at against any manifest
   it finds — the wrong toolchain for a repo that declares its own. Inside
   each new worktree, bootstrap only the package kinds the project actually
   declares, with the tooling the project itself names:
   - If the project declares a Python dependency environment, sync it with
     the project's declared package manager — never an auto-detected
     substitute; a stdlib-only python3 project needs nothing here.
   - If the project has a JavaScript/TypeScript package (package.json at
     repo root or in a UI subdirectory), run `npm ci` inside its directory —
     never `npm install`, which can mutate the lockfile. Do **not** replace
     this with a copy-on-write clone of the main checkout's `node_modules`
     to save time: measured 2026-09-21 on one machine, `npm ci` against a
     lockfile took **2.151s** for all 365 entries (265 MB) because npm
     hardlinks from its own warm global cache, while `cp -Rc` of the same
     tree took **2.962s** — the clone is slower, and it gives up npm's
     integrity verification as well. The measurement holds only while that
     global cache is warm, which it is in this workflow's own conditions: a
     worktree is created on a machine whose main checkout is already
     installed.
   - If the project ships an additional JavaScript/TypeScript subpackage
     with no lockfile (e.g. a tool package whose type-check a pre-commit
     hook runs on every commit touching its files), link (never install)
     that subpackage's `node_modules` from the main checkout:
     `ln -s <main-checkout-absolute-path>/<subpackage-path>/node_modules
     <subpackage-path>/node_modules` (run from the new worktree). The hook
     needs a real `node_modules` to resolve against, and `npm ci` cannot
     install one from a package with no lockfile the way it does for a
     locked package; linking to the main checkout's already-installed tree
     avoids both that dead end and installing a second full copy per
     worktree. A link is safe here where sharing one `node_modules` between
     concurrent worktrees generally is not, and the reason is narrow: the
     linked package's tree is only ever read by a type-check, so nothing
     writes a cache into it. A locked package's `node_modules` by contrast
     holds live scratch directories its own tooling writes during a lint or
     test run, which is why those are installed per worktree rather than
     shared. `.gitignore`'s `node_modules` pattern (no trailing slash, so it
     matches the symlink and not only a real directory) keeps the link
     itself out of every diff.
3. **Never fall back to working in place on the shared checkout when a
   worktree cannot be acquired.** That recreates the exact shared-checkout
   hazard this whole workflow
   exists to avoid. The acquire script's own refusals are not creation
   failures: an exit 1 (your run's N slots are in use) means the group **waits
   for a slot** — leave it at `Grouped`, re-poll next turn, and let an
   earlier group's Step 6 release free its slot automatically; never edit
   `.agents/config.toml` to make room (N is human-only). An exit 2
   (undecidable input — unparseable git output, a missing or invalid
   config) is a halt trigger: fail closed, halt all further acquisition,
   and report the script's stderr to the human. Treat a failed/timed-out
   bootstrap (dependency sync or package install) inside a freshly acquired
   worktree the same way.
   Present the human an explicit choice, shaped by how
   far the run had already gotten:
   - **No group has a worktree yet** (halted on the very first attempt):
     fix the underlying problem and retry, or demote the whole run to
     serial execution — one worktree, one group at a time, every other rule
     in this workflow unchanged. Demoting still means acquiring that one
     worktree through the same
     `.agents/scripts/worktree_acquire.py acquire` call — never working in place on
     the shared checkout, and never a tool that writes to
     `.claude/worktrees/`, for the same reason.
     If the halt was environmental (disk,
     permissions, a broken language or package toolchain), demoting alone
     will not
     fix it — report that plainly rather than letting a second failure
     inside the demoted flow silently resolve into working on the main
     checkout unbranched.
   - **Some groups already have live worktrees** (the halt landed partway
     through fan-out): report how many succeeded and how many are
     blocked, then offer bounded concurrency (let the already-started groups
     finish and land before starting any more) or serial fallback for
     only the not-yet-started remainder — the already-started groups keep
     running as they are.
4. Each worktree gets its own plan workspace automatically. Run
   `python3 .agents/scripts/sdd_workspace.py PLAN_FILE` inside the worktree and
   use the directory
   it prints — **this file calls that directory `<plan-workspace>` throughout,
   and never writes the path by hand.** It resolves to
   `<worktree-root>/docs/runs/<plan-file-basename>/`: the
   script derives the trailing component with `basename "$plan" .md` semantics,
   not from
   the run, group, or spec slug, and the root comes from `git rev-parse
   --show-toplevel`, which inside a worktree is that worktree's own path — so
   no extra namespacing is needed. The ledger is `<plan-workspace>/progress.md`.
   The flat `docs/runs/progress.md` is **not** that file — it is the old flat
   path, and a controller that finds one leaves it in place as another plan's
   progress and starts fresh.
5. Record every group's worktree path, branch name, and state (`Grouped` →
   `WorktreeReady`) in the run-state file (see below) as it is created.

A group with only one task still gets a full worktree, branch, and ledger —
isolation is earned by having a disjoint file set, not by task count.

