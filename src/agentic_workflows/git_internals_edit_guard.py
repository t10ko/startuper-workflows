"""Block file-edit tools from writing the state this repository's guards read.

`git_write_guard` blocks git's own mutating commands at the shell-command
layer, but that guard only inspects `Bash` invocations. A file-edit tool
(Edit/Write/NotebookEdit) reaches the same state directly, so this module
closes that second route — for whole **path classes, not filename matches**.

## Class 1 — git's administrative area

Two members:

1. Any path at or below a `.git` entry — `<checkout>/.git/**` (config, hooks,
   HEAD, refs, objects, the per-worktree `worktrees/<name>/**` records), and
   the entry itself. A linked worktree's own `.git` is a *file* whose `gitdir:`
   line names the checkout that every later authorization decision is anchored
   on (`src/utils/git_checkout_resolution.py`), so rewriting it re-points the
   ownership model wholesale — the hazard `.agents/rules/agent-worktrees.md`
   records. A filename predicate cannot see it: the file is named `.git`.
2. The per-user git configuration git reads for every repository on the host —
   `~/.gitconfig` and `<config home>/git/**`. `git config --global` is denied
   unconditionally on the Bash route, so leaving these writable here would
   reopen the exact bypass this module exists to close: `core.hooksPath` set
   there disables this repository's commit gate from outside the repository.

## Class 2 — a plan-run authorization record

Anything at or below `PLAN_RUNS_DIR`, whose value is imported from
`src.utils.plan_run_paths` rather than restated here. The push gate reads the
record for the branch being pushed and authorizes the push only when the commit
it would send equals both recorded SHAs — the ones this round's `make verify`
and secret scan actually ran against (`git_push_authorization`).
The record is an ordinary Markdown file, so the agent whose push it authorizes
can write its own authorization: measured here, rewriting the two SHAs turns
"push denied: pushed commit does not match this round's verify-status SHA" into
an authorized push, with no git command anywhere in the forgery.

Refusing the whole class costs the workflow nothing: only the orchestrating
session writes this record, and it does so through `plan_run_state`'s typed
API, never a file-edit tool. The rest of `docs/runs/` stays writable —
the vendored per-task ledger and each group's notes live there and every
implementer writes them.

## Where a relative path points

A file-edit tool accepts a relative `file_path`, and the tool layer resolves it
against the working directory it reports in the hook payload — measured on this
harness, a bare filename written that way was created under the session's own
directory. That reported directory is the only base these predicates use. The
hook process's own directory is whatever the tool layer happened to start it in
and is never consulted, so one identical payload can no longer block from one
directory and pass from another. A relative path with no absolute working
directory to anchor it is undecidable, not benign, and is refused — the same
posture `git_write_guard` states for every rule of its own that depends on
`cwd`.

## What these predicates do NOT reach

- Any route other than a file-edit tool. A Bash-issued write is the subject
  of the companion `src/utils/protected_path_write_guard.py`
  (`.claude/hooks/block_protected_path_write.py`, matcher `Bash`), which
  refuses the shapes a shell command names in its own operands — the
  `printf > <record>`, `sed -i`, `tee` and `cp` spellings this module
  measured open are refused there. What stays open on that route is an
  interpreter writing through its own runtime (`python -c`, a `uv run`
  script), the same route the orchestration's own legitimate record write
  travels, so the companion states that hole rather than claiming the route
  closed.
- System configuration (`/etc/gitconfig`) and the `GIT_CONFIG_SYSTEM`,
  `GIT_CONFIG_GLOBAL`, and `GIT_DIR` environment overrides, all of which can
  relocate a member of this class to a path with no `.git` component.
- An administrative directory not named `.git`: a bare repository (`repo.git/`
  holds `config`, `HEAD` and `objects/` at its own root) and a checkout created
  with `--separate-git-dir`.
- A `core.hooksPath` pointing outside the administrative area. This repository
  sets it to `<main checkout>/.git/hooks`, which member 1 covers; a different
  value would not be covered.
- Symlink-mediated reach where neither the path as written nor its resolved
  form lands in the class.
- A hard link, whose target shares no path component with the file it aliases.
  `resolve()` follows symlinks only; a second name for `.git/config` or for a
  plan-run record created with `ln` is a different path by every test here, and
  writing through it changes the original. The mirror case escapes the same
  way: a symlink *placed at* a protected path sends a write to wherever it
  points, while the gate that reads the protected path follows it right back.
  Both need a Bash `ln`, which no guard in this repository inspects.

Deliberately over-approximates in three directions for both classes, all of
them free: a path whose written form carries a protected component but whose
resolved form leaves the class (`.git/../README.md`); any component that
*folds* to a protected name (`.GIT`, `.git.`, a compatibility-normalized
spelling), whether or not this host's filesystem actually aliases it; and any
path this module cannot resolve at all. Refusing a path nothing writes costs
nothing; failing to refuse one is the defect this module exists to prevent.

The third of those refusals says what it is. An undecidable path gets
`UNDECIDABLE_PATH_MESSAGE` rather than a class message, because the class it
would have landed in is exactly what could not be decided — a denial names the
fact behind it, and a specific reason that is false is worse than an honest
general one. A path whose written form already places it in a class is decided
there without resolving anything, so an unresolvable path inside a class is
still named as that class.
"""

from __future__ import annotations

import os
import unicodedata
from collections.abc import Callable
from pathlib import Path

from agentic_workflows.plan_run_paths import PLAN_RUNS_DIR

# git's own name for a repository's administrative entry — a directory in the
# main checkout, a pointer file in a linked worktree.
GIT_ENTRY_NAME = ".git"

# The per-user configuration git applies to every repository on the host.
USER_CONFIG_FILENAME = ".gitconfig"
XDG_GIT_CONFIG_DIRNAME = "git"

# `Path.resolve()` raises more than `OSError`: measured on CPython 3.12.12, a
# symlink loop surfaces as `RuntimeError` and an embedded NUL as `ValueError`.
# Catching only `OSError` left both uncaught, and an uncaught exception in the
# hook is a NON-blocking error the tool proceeds past — a fail-open dressed as
# a fail-closed.
RESOLUTION_FAILURES = (OSError, RuntimeError, ValueError)


def _normalize_component(component: str) -> str:
    """One path component reduced to a form that survives the ways a
    filesystem may consider two spellings the same file.

    Case-folded because this repository's own checkout sits on a
    case-insensitive volume: `<worktree>/.GIT` and `<worktree>/.git` are one
    file there, and `git_checkout_resolution.find_git_entry` looks the anchor
    up as `directory / ".git"` — so a write spelled in another case lands on
    the pointer file the whole ownership model is read from. Trailing dots and
    spaces are dropped because Windows discards them when opening a file, and
    compatibility characters are normalized for the same reason. On a
    case-sensitive volume `.GIT` really is a different directory and refusing
    it is over-approximation, which this module already prefers to a miss."""

    return unicodedata.normalize("NFKC", component).rstrip(". ").casefold()


def _normalized_parts(path: Path) -> tuple[str, ...]:
    return tuple(_normalize_component(part) for part in path.parts)


NORMALIZED_GIT_ENTRY_NAME = _normalize_component(GIT_ENTRY_NAME)
NORMALIZED_PLAN_RUNS_PARTS = _normalized_parts(PLAN_RUNS_DIR)


def _xdg_config_home() -> Path | None:
    """The XDG configuration root git reads `git/config` under, or None when
    neither the environment nor a home directory can establish one."""

    configured = os.environ.get("XDG_CONFIG_HOME")
    if configured:
        return Path(configured)
    try:
        return Path.home() / ".config"
    except RuntimeError:
        return None


def _home_directories() -> list[Path]:
    """The user's home directory as written and as resolved — a symlinked home
    would otherwise place `~/.gitconfig` outside the class in one of the two
    candidate forms `is_git_internals_path` tests."""

    try:
        home = Path.home()
    except RuntimeError:
        return []
    try:
        return [home, home.resolve()]
    except RESOLUTION_FAILURES:
        return [home]


def _is_user_git_configuration(parts: tuple[str, ...]) -> bool:
    """True for the per-user git configuration files: `~/.gitconfig` and
    anything under `<config home>/git/`. Compared component-wise in normalized
    form, so `~/.GitConfig` and `<config home>/GIT/config` are the same
    members they are on the volume this repository runs on."""

    if any(
        parts == _normalized_parts(home / USER_CONFIG_FILENAME)
        for home in _home_directories()
    ):
        return True

    config_home = _xdg_config_home()
    if config_home is None:
        return False
    git_root = _normalized_parts(config_home / XDG_GIT_CONFIG_DIRNAME)
    return len(parts) > len(git_root) and parts[: len(git_root)] == git_root


def _is_inside_administrative_area(parts: tuple[str, ...]) -> bool:
    """True when `parts` names a `.git` entry or lies below one, or names
    per-user git configuration."""

    return NORMALIZED_GIT_ENTRY_NAME in parts or _is_user_git_configuration(parts)


def _starts_a_component_run(parts: tuple[str, ...], run: tuple[str, ...]) -> bool:
    """True when `run` appears as consecutive components of `parts` — the
    directory itself, or anything below it, wherever it sits."""

    return any(
        parts[start : start + len(run)] == run
        for start in range(len(parts) - len(run) + 1)
    )


def _is_plan_run_record(parts: tuple[str, ...]) -> bool:
    """True when `parts` names the directory the push gate's authorization
    records live in, or anything below it."""

    return _starts_a_component_run(parts, NORMALIZED_PLAN_RUNS_PARTS)


def _anchor(expanded: Path, cwd: Path | None) -> Path | None:
    """`expanded` made absolute against the working directory the TOOL LAYER
    reported for this call, or None when no absolute base exists.

    A relative `file_path` names a file under the session's own directory —
    measured on this harness, a bare filename written through a file-edit tool
    was created there — and the payload carries that directory in its `cwd`
    field, exactly as the Bash-route hook already reads it. This hook process's
    own directory is whatever the tool layer happened to start it in and is
    never consulted: `Path.resolve()` on a relative path would silently use it,
    which made one identical payload block from one directory and pass from
    another. A relative `cwd` is no base either — it would hand the decision
    straight back to the process — so it fails closed like an absent one."""

    if expanded.is_absolute():
        return expanded
    if cwd is None or not cwd.is_absolute():
        return None
    return cwd / expanded


def _class_verdict(
    file_path: Path | None,
    member: Callable[[tuple[str, ...]], bool],
    cwd: Path | None,
) -> bool | None:
    """Whether `file_path` falls in `member`'s class: True inside, False
    outside, **None when the path's real location cannot be established at
    all**.

    The third state is the whole point. Every form of the path is tested — as
    written (with `~` expanded), anchored at the reported working directory,
    and fully resolved — and each component is compared in the normalized form
    a filesystem may itself compare it in. A path the written form already
    places in the class is decided there and needs no resolution, so an
    unresolvable path inside a class is still reported as that class rather
    than as an unknown. Everything else that cannot be established is None,
    which every caller here turns into a refusal — being unable to rule a path
    out is not evidence it is safe — but a refusal that says so, instead of
    naming a class it never actually matched."""

    if file_path is None:
        return False

    try:
        expanded = file_path.expanduser()
    except RuntimeError:
        return None

    if member(_normalized_parts(expanded)):
        return True

    anchored = _anchor(expanded, cwd)
    if anchored is None:
        return None

    try:
        resolved = anchored.resolve()
    except RESOLUTION_FAILURES:
        return None

    return member(_normalized_parts(anchored)) or member(_normalized_parts(resolved))


def git_internals_verdict(
    file_path: Path | None, cwd: Path | None = None
) -> bool | None:
    """Whether `file_path` is inside git's administrative area: True, False, or
    None when its real location could not be established.

    The tri-state is public because a *second* route to these same paths — the
    Bash companion in `protected_path_write_guard` — has to tell "inside this
    class" from "could not be decided" to name its refusal honestly, and
    folding them into one boolean here would force that caller to reinvent the
    distinction or report a class it never matched."""

    return _class_verdict(file_path, _is_inside_administrative_area, cwd)


def plan_run_record_verdict(
    file_path: Path | None, cwd: Path | None = None
) -> bool | None:
    """Whether `file_path` is a plan-run authorization record: True, False, or
    None when its real location could not be established."""

    return _class_verdict(file_path, _is_plan_run_record, cwd)


def is_git_internals_path(file_path: Path | None, cwd: Path | None = None) -> bool:
    """True when `file_path` targets git's administrative area, or when its
    location cannot be established — an undecidable path is refused."""

    return git_internals_verdict(file_path, cwd) is not False


def is_plan_run_record_path(file_path: Path | None, cwd: Path | None = None) -> bool:
    """True when `file_path` targets the push gate's authorization record for
    some run — the directory `PLAN_RUNS_DIR` names, or anything below it — or
    when its location cannot be established."""

    return plan_run_record_verdict(file_path, cwd) is not False


#: One name per class, so the two routes that refuse these paths — the
#: file-edit hook here and the Bash companion in `protected_path_write_guard` —
#: cannot drift into calling the same class two different things.
GIT_INTERNALS_CLASS_NAME = "git's administrative area"
PLAN_RUN_RECORD_CLASS_NAME = "a plan-run authorization record"

UNDECIDABLE_PATH_MESSAGE = (
    "Blocked edit to a path whose real location could not be established. "
    "This guard refuses what it cannot rule out rather than permitting what it "
    "cannot rule in, so a path that resolves into a symlink loop, carries an "
    "embedded NUL, arrives relative with no working directory to anchor it, or "
    "sits under a home directory that cannot be determined is refused here. "
    "This is NOT a report that the path fell in either protected class — which "
    "one it would land in, if any, is precisely what could not be decided, and "
    "naming a class here would send you to debug a problem you may not have. "
    "Write the path in a form that can be resolved and retry."
)


def build_git_internals_edit_block_message(
    file_path: Path | None, cwd: Path | None = None
) -> str | None:
    """Return a user-facing block reason for an edit inside git's
    administrative area, or None when the path is outside it. An undecidable
    path is still refused, with the reason that actually applies."""

    verdict = git_internals_verdict(file_path, cwd)
    if verdict is None:
        return UNDECIDABLE_PATH_MESSAGE
    if not verdict:
        return None

    return (
        f"Blocked edit to a path inside {GIT_INTERNALS_CLASS_NAME}. Agents may "
        "not write a `.git` entry, anything under one, or the per-user git "
        "configuration — this class covers `.git/config`, a linked worktree's "
        "`config.worktree` and its own `.git` pointer file (rewriting which "
        "re-points the ownership anchor every later authorization decision is "
        "made against), the shared `.git/hooks` directory, refs and objects. "
        "See .agents/rules/agent-worktrees.md and "
        ".agents/rules/block-git-mutations.md. If such a change is genuinely "
        "needed, ask the user to make it."
    )


def build_plan_run_record_edit_block_message(
    file_path: Path | None, cwd: Path | None = None
) -> str | None:
    """Return a user-facing block reason for an edit to a plan-run
    authorization record, or None when the path is outside that class. An
    undecidable path is still refused, with the reason that actually applies."""

    verdict = plan_run_record_verdict(file_path, cwd)
    if verdict is None:
        return UNDECIDABLE_PATH_MESSAGE
    if not verdict:
        return None

    return (
        f"Blocked edit to {PLAN_RUN_RECORD_CLASS_NAME}. The push gate reads "
        f"`{PLAN_RUNS_DIR.as_posix()}/<branch>.md` to decide whether the commit "
        "being pushed is the one this round's verification and secret scan ran "
        "against, so an agent that can write this file authorizes its own "
        "push. Only the orchestrating session writes it, through "
        "`src.utils.plan_run_state`'s write_plan_run_state / "
        "update_plan_run_state — never a file-edit tool. The vendored ledger "
        f"and the group notes elsewhere under `{PLAN_RUNS_DIR.parent.as_posix()}/` "
        "stay writable. If this record genuinely needs a manual change, ask "
        "the user to make it."
    )


def build_protected_edit_block_message(
    file_path: Path | None, cwd: Path | None = None
) -> str | None:
    """The hook's single entry point: the reason specific to whichever
    protected class `file_path` falls in, or None when it falls in neither.
    Never one shared reason for both: a denial names the specific fact behind
    it, so the reader learns which class they hit and why it is guarded.

    A class that actually decided outranks one that could not, so an
    unresolvable path inside a protected class is still named as that class;
    only a path no class could decide gets the undecidable reason. Reporting
    such a path as an administrative-area edit — which asking one class first
    and reading its fail-closed True as a match used to do, for any undecidable
    path including one with no protected component at all — is a specific
    reason that is false, and sends a blocked agent to debug a git problem it
    does not have."""

    internals = git_internals_verdict(file_path, cwd)
    if internals is True:
        return build_git_internals_edit_block_message(file_path, cwd)

    record = plan_run_record_verdict(file_path, cwd)
    if record is True:
        return build_plan_run_record_edit_block_message(file_path, cwd)

    if internals is None or record is None:
        return UNDECIDABLE_PATH_MESSAGE

    return None
