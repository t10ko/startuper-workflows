"""Refuse a Bash-issued write to a path this repository's own guards read.

`git_internals_edit_guard` closes the *file-edit* route to two protected path
classes — git's administrative area, and the plan-run authorization record the
push gate reads. It says so itself, four times over, and it is right: an agent
holding the `Bash` tool reached the same paths with `printf >`, `sed -i`,
`tee`, `cp`, `dd of=`, `mv`, `ln`, a `cd` plus a bare relative redirect, and an
append — measured before this module existed, each one rewrote the record and
turned "push denied: pushed commit does not match this round's verify-status
SHA" into an authorized push, with no git command anywhere in the forgery.

This module is that route's companion. It composes two things it does not own:
`shell_write_targets.write_targets` says which paths a command is found to
write, and `git_internals_edit_guard`'s two tri-state verdicts say whether a
path is protected. It adds one decision of its own — what to do about a write
it cannot read — and states it below.

## Route, not actor

The orchestration writes the same record legitimately, and no guard can tell
*who* issued a command. What it can tell is the **route**: the orchestration
reaches the record through `plan_run_state`'s typed API, so its command string
carries no operand naming the file at all, while a forgery reaches it as raw
text manipulation whose operand is the path. Measured on the documented idiom,
`uv run python -c "... update_plan_run_state(...)"` yields no target and no
doubt, and `sed -i '' 's/…/…/' <record>` names the record.

That distinction is real, and it is also **exactly the structural hole** in the
recognizer: an interpreter writing through its own runtime is invisible, so an
agent spelling its forgery as `python -c "open(<record>,'w')…"` passes here for
the same reason the orchestration does. One fact, not two. This module closes
the shapes a shell states in its own operands, and nothing more — see "What
this does NOT reach".

## An unreadable target is a refusal; an uncertain write is not

`write_targets` reports a doubt rather than falling silent whenever it cannot
read a write, and it gives each doubt a **kind**. The policy differs by kind,
and both halves are stated here because a reader meets the friction of one and
the residual hole of the other.

`DoubtKind.UNREADABLE_TARGET` — a recognized shape definitely writes, and which
file it writes cannot be read: a variable, a command substitution, a glob, a
brace expansion, an operand the shell removed, a relative operand after an
unmodelled `cd`, or a command that will not tokenize. **Every one of those is
refused.** Being unable to rule a write out is not evidence it is safe, and it
is the posture `git_write_guard` already takes for every rule of its own that
depends on a working directory. Failing open here was rejected outright:
`T=.git/config; printf x > "$T"` is one line, and a guard that permits it
protects nothing an attacker cannot spell around.

The cost was measured, not assumed, on the 385 real command lines this
repository's `Makefile` recipes and `scripts/**/*.sh` produce — the corpus
`test_the_over_block_cost_on_this_repositorys_own_commands` keeps executable.
Zero writes a protected path; **18 are refused for an unreadable target**, of
which two are whole runnable commands (`rm -rf books/*/.conversations`, a
glob; `cp … server-${TRIPLE}`, a variable) and the rest are fragments of a
continued `Makefile` command that do not tokenize on their own. Each has a
decidable spelling, and the denial says so.

Modelling what an expansion *could* become — brace expansion is syntactic and
enumerable, and a glob never crosses `/` nor matches a leading dot — would
recover three of those five, and is deliberately not done: it would be a
second, independent owner of "what can this operand become", whose every
mistake fails **open**, on the boundary this guard exists to hold.

`DoubtKind.UNCERTAIN_WRITE` — a `>` inside a quoted word, where it is not
established that a write is happening at all. **This one is allowed**, and the
reason is measured on both sides:

- Refusing it blocks everyday work. Of the 5,923 commit-message lines in this
  repository's history, 95 carry a `>` — arrows (`A -> B`) and the
  `Co-Authored-By: … <noreply@…>` trailer among them — and every one reaches a
  shell as a quoted word, whether in `git commit -m`, `rg -n 'a -> b' src` or
  `echo "x > y"`.
- Refusing it closes nothing. `bash -c "printf x > <path>"` is one spelling of
  the interpreter hole in item 1 of "What this does NOT reach" below, which is
  wide open in every other spelling — `bash -c "python -c …"`, `xargs sh -c`,
  a script file — none of which this guard can see. Paying an everyday
  over-block for one spelling of an unrefusable class buys no coverage.

So the honest statement is: a shell command that writes a protected path from
*inside a quoted body it hands to another interpreter* is **not** refused here,
and never was going to be.

## Which working directory

The one the tool layer reports in the hook payload — the shell's own directory,
the base a relative operand resolves against. This module never consults
`os.getcwd()`, and passes `cwd` into both predicates so they anchor there too.
A relative target with no absolute `cwd` is undecidable and refused, exactly as
it is on the file-edit route.

## What this does NOT reach

Everything `shell_write_targets` declares it cannot see propagates here
verbatim, and this guard adds nothing to that list's coverage:

1. **An interpreter writing through its own runtime** — `python -c`, `uv run
   python <script>`, `perl -e`, `node -e`, `awk`, a `Makefile` target, a
   compiled binary. The structural hole, and the same hole the orchestration's
   own legitimate write passes through.
2. **A writing command outside the recognizer's table** — `patch`, `rsync`,
   `tar -x`, `unzip`, `sort -o`, `git apply`, `git checkout -- <path>`, any
   editor. A bulk writer's destinations live in an archive or a diff, not in
   the command.
3. **A mid-word command substitution**, which leaves no trace at all:
   `curl -o $(echo <path>) <url>` is silent rather than doubtful, and
   `tee logs/run-$(date +%s).log` reports a *false* target.
4. **Shell constructs not modelled** — `eval`, aliases and functions, process
   substitution, and a `cd` whose destination is computed.
5. **A link made by some earlier command or by a file-edit tool.** Only an `ln`
   inside *this* command string is visible; a hard link created a minute ago
   turns an innocuous path into a write of whatever it aliases.

Beyond the recognizer's own list, two limits belong to this guard: it is
attached to the `Bash` tool only, so any other tool that reaches a shell is not
inspected; and it judges one command in isolation, with no memory of what
earlier commands in the session created.
"""

from __future__ import annotations

from pathlib import Path

from agentic_workflows.git_internals_edit_guard import (
    GIT_INTERNALS_CLASS_NAME,
    PLAN_RUN_RECORD_CLASS_NAME,
    git_internals_verdict,
    plan_run_record_verdict,
)
from agentic_workflows.shell_write_targets import (
    Doubt,
    DoubtKind,
    WriteTarget,
    write_targets,
)

#: Why each class is guarded, in the terms a blocked agent needs: the fact the
#: write would change, not merely the name of the directory it sits in.
CLASS_CONSEQUENCE = {
    GIT_INTERNALS_CLASS_NAME: (
        "Writing, moving, deleting or unsetting the execute bit on anything "
        "there defeats a control this repository relies on — `.git/hooks` "
        "carries the commit gate, `.git/config` carries `core.hooksPath`, and "
        "a linked worktree's own `.git` pointer file names the checkout every "
        "later authorization decision is anchored on. See "
        ".agents/rules/agent-worktrees.md and "
        ".agents/rules/block-git-mutations.md."
    ),
    PLAN_RUN_RECORD_CLASS_NAME: (
        "The push gate reads that record to decide whether the commit being "
        "pushed is the one this round's verification and secret scan actually "
        "ran against, so an agent that can write it authorizes its own push. "
        "Only the orchestrating session writes it, through "
        "`src.utils.plan_run_state`'s write_plan_run_state / "
        "update_plan_run_state — never a shell command."
    ),
}


def _undecidable_message(reasons: list[str]) -> str:
    """The refusal for a write this guard could not read. It names neither
    class: which one the target would land in, if any, is precisely what could
    not be decided, and a specific reason that is false sends a blocked agent
    to debug a problem it does not have."""

    return (
        "Blocked: this command writes a file whose path could not be "
        "established, and this guard refuses what it cannot rule out rather "
        "than permitting what it cannot rule in. Reason: "
        + "; ".join(reasons)
        + ". This is NOT a report that the path is protected — write the "
        "target as a literal path and retry, or reach the file through a "
        "typed API instead of the shell."
    )


def _protected_message(target: WriteTarget, class_name: str) -> str:
    return (
        f"Blocked: this command writes `{target.path.as_posix()}` (read as the "
        f"{target.shape}), which is inside {class_name}. "
        + CLASS_CONSEQUENCE[class_name]
        + " If this change is genuinely needed, ask the user to make it."
    )


def build_protected_path_write_block_message(
    command: str, cwd: Path | None = None
) -> str | None:
    """A user-facing reason to refuse `command`, or None to allow it.

    `cwd` is the working directory the tool layer reported for this call — the
    base every relative operand resolves against. It is the only base used;
    this module's own process directory never enters the decision.

    A target this guard actually *decided* is protected outranks one it could
    not read, so a denial names the fact behind it rather than the first doubt
    it happened to meet."""

    found = write_targets(command)

    unreadable: list[Doubt] = [
        doubt
        for doubt in found.undecidable
        if doubt.kind is DoubtKind.UNREADABLE_TARGET
    ]
    for target in found.targets:
        for class_name, verdict in (
            (GIT_INTERNALS_CLASS_NAME, git_internals_verdict(target.path, cwd)),
            (PLAN_RUN_RECORD_CLASS_NAME, plan_run_record_verdict(target.path, cwd)),
        ):
            if verdict is True:
                return _protected_message(target, class_name)
            if verdict is None:
                unreadable.append(
                    Doubt(
                        DoubtKind.UNREADABLE_TARGET,
                        f"{target.shape}: the real location of "
                        f"`{target.path.as_posix()}` could not be established",
                    )
                )

    if unreadable:
        return _undecidable_message(
            list(dict.fromkeys(doubt.reason for doubt in unreadable))
        )
    return None
