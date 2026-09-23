# A Noticed-But-Unfixed Finding Goes In A Decision Note

Recorded 2026-08-21 at the user's direction, after a 115-task run scattered
findings across code comments and a run-state file with no single place to read
them.

## The rule

**A problem you notice and do not fix is recorded in a decision note under
`docs/decision-notes/`, and nowhere else.** Never in a code comment or
docstring, a plan, a run-state record under `docs/runs/`, a commit message,
or a chat summary only the current session can see.

## What counts

Anything wrong, missing, unowned or unproven that you did not repair in the
change at hand: a defect outside scope; a gap no task owns; a guard that cannot
fire or is blind to a class of failure; a value with two owners nothing
collapses; a spec or plan claim measurement contradicted; a rule enforced but
never delivered to the producer held to it.

**The test:** if the problem were fixed, would the note be deleted rather than
edited? Then it is a finding.

## What is not a finding

Ordinary code prose stays where it is — a comment explaining **why** code is
shaped as it is, a measurement supporting a design choice, a correct and closed
deliberate exclusion, or a stated limit of what a check covers. A boundary says
what the code does; a finding says what is wrong somewhere else.

## Why not a comment, a plan, or a run-state file

A comment reaches whoever opens that file for some other reason. It is
invisible to anyone asking "what is still open?", it carries no severity and no
owner, nothing marks it resolved when someone fixes it, and it dies silently
when the file is refactored away.

A plan and a run-state record are both scoped to one piece of work and stop
being read the moment it lands. A plan states what will be done; a finding
states what is wrong. Mixing them hands the plan's readers a backlog they did
not ask for, and loses it when the plan finishes.

## How to write it

Follow `.agents/workflows/deliberation.md`'s note format. One note may hold many
findings — a register per subject beats a note per finding. Each entry states:

- **What is wrong**, actionable by a reader without your context.
- **Where** — file and line, or the contract or requirement it belongs to.
- **Severity** — what breaks, and whether today or only after some future change.
- **Why it was not fixed here** — scope, cost, or a decision that is not yours.
- **Who could own it** — a named task, a future one, or nobody yet.

State it as measured, not suspected. A finding that says "unverified" is worth
more than one that overstates.

## Consent

Writing under `docs/decision-notes/` needs the user's approval, exactly as
`.agents/workflows/deliberation.md` requires. Ask with `AskUserQuestion` and
wait for a clear yes.

If approval is not available in the moment, **say the finding in your reply to
the user** and keep it out of the code. A finding stated in chat and lost beats
one buried in a comment and mistaken for coverage.

When a parallel-subagent-driven-development run executes under `--dont-defer`,
the invoking command's flags authorize one decision-note register for the run's
refused-and-reported findings, written at run end: no separate per-note consent
ask is needed, because the flags themselves authorize that single register
write. The register is an ordinary note under `docs/decision-notes/`, formatted
as above — the flags pay for that one write and nothing beyond it.

The project's own gap/tradeoff doc, if it keeps one, is a separate, narrower
gate — see
`.agents/rules/memory-consent.md`. It carries a finding the project has decided
to live with; the register here is where one starts.
