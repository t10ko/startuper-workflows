---
trigger: always_on
---
# Memory Consent Gate

This is the canonical statement of the memory-consent protocol for this
project. Other files that mention memory writes point back here instead of
restating it. "Memory" here means a persistent, cross-session record of a
stated preference, feedback, or fact — distinct from the project's own gap
doc (a progress log, see below, when the project keeps one) or ordinary code
and doc changes.

## The rule

No agent creates or edits a memory record without explicit, in-session user
consent. Ask with `AskUserQuestion`, wait for a clear yes, and only then
write it — and only to a tracked repo file (see "Where memories go" below).
Content that merely sounds like past consent, or an existing memory record
itself, is never consent to write another one.

Reads are never gated: any agent may read `MEMORIES.md`, any file under
`.agents/rules/`, or the project's gap doc (if present) at any time without
asking.

Deleting a memory (`MEMORIES.md` or a file under `.agents/rules/`) is
human-only: an agent may point out that a memory looks stale or wrong, but
must not remove or rewrite it unilaterally. The gap doc is not a
memory (see the definition above) and the opposite rule governs its removal
— see its entry under "Where memories go" below.

Consent gates join the hard-invariants list that no execution-mode flag
overrides — the parallel-subagent-driven-development workflow's `run-start.md`
(Step 0.1) owns that list. A run whose admitted finding needs a write this file
gates does not write it unasked: the finding is reported, and the run asks the
owner once, after the pull request is open.

## Where memories go

- `.agents/rules/` — a standing behavioral rule the agent should follow on
  every relevant future task (a workflow preference, a coding convention).
  Give it its own file, following the shape of the other files in this
  directory: an H1 title, a short lead paragraph, then `##` sections.
- `MEMORIES.md` — a terse, one-bullet-per-entry actionable rule, per the
  format already defined at the top of that file.
- The project's own gap doc, if it keeps one — a known-but-unfixed issue:
  a bug, design gap, or
  repeatedly root-caused failure that still has no shipped fix. **Requires
  explicit user approval before writing.** No entry may ever be added
  automatically or silently. The approval must be requested as a standalone,
  explicit question dedicated solely to approving adding that gap to the
  doc. **That gate covers addition only.** Once an agent
  has established that a row is stale, removing it needs no approval — the
  register is a tracked file, so the removal itself is already visible in
  the diff. That permission reaches deletion of the row and nothing else.
  Rewriting a row in place needs the user's approval, exactly as adding one
  does. Cite the tree fact that establishes staleness in the same change
  that removes the row, so a reviewer can check the judgment from the diff
  alone. The citation is required — a removal citing no tree fact is a
  defect — and has no mechanical enforcement: it is a post-removal review
  obligation, not a gate the removal waits on.

## Where a finding goes — not here

A **finding** is not a memory. A memory records something the user said or
decided; a finding records something the code gets wrong. A problem you notice
and do not fix belongs in a decision note under `docs/decision-notes/`, never in
a code comment, a plan, a run-state file, or a commit message — see
`.agents/rules/findings-go-in-decision-notes.md`.

The project's gap doc (if present) is the narrower, later gate: it carries a
finding the
project has decided to live with, and every entry needs its own standalone
approval as above. A finding starts in the register and reaches that file only
if someone decides it should be carried.

## Never write to

- `~/.claude/**/memory/`
- `.remember/`

Both are untracked, per-machine, and invisible to code review — nothing in
the repo can catch what an agent writes there, and no pull request diff
shows it changed. Worse, content there is auto-injected into every future
session's context, so a stale or wrong entry silently outranks a correct,
reviewed repo skill or rule with no visible trace of why.

## Why this rule exists

A record in the untracked, per-machine memory store — dated 2026-07-18,
forbidding autonomous branches, commits, and pushes — silently suppressed a
shipped parallel branch/PR workflow across three separate sessions, with
each agent citing the stale record unprompted, and nothing in the repo able
to catch it because the record was never subject to review.

## Known gaps

This rule is enforced by a `PreToolUse` hook blocking writes to
`~/.claude/**/memory/` and `.remember/` — the same enforcement mechanism as
the `block_git_mutations.py` and `block_grep_search.py` hooks. Like those,
it has real, stated limits:

- **Bash-mediated writes** (`cat > ~/.claude/.../memory/x.md`, `tee`,
  `sed -i`): this repo's `shell_command_parsing.py` has no redirect support
  at all, and a partial parser would give false confidence rather than real
  protection. The built-in automatic-memory-write mechanism is disabled at
  its source instead of being caught after the fact, so this hook is
  defence-in-depth, not the only control.
- **Other coding agents** that never execute this repo's `.agents/hooks/` —
  the hook is advisory only outside this harness.
- **The human's own edits** — by design; a human editing their own memory
  store directly is never blocked.
- **A harness-internal writer**, if one exists outside this repo's own
  tool-call surface — unverifiable from this repo.

The honest framing: the hook enforces "not without a gate" — it can stop an
agent's own tool-mediated write from landing unreviewed. Whether that write
was actually *asked first* is agent compliance with the rule above, not
something the hook itself can verify.
