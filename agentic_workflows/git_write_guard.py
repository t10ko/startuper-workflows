from __future__ import annotations

from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Literal, NamedTuple, Protocol

from agentic_workflows.git_checkout_resolution import (
    cwd_is_linked_worktree,
    enclosing_checkout_root,
    is_agent_owned_worktree,
    main_checkout_root,
)
from agentic_workflows.git_push_authorization import push_denial_reason
from agentic_workflows.git_state_scope import WORKTREE_LOCAL_SUBCOMMANDS, scope_denial_for
from agentic_workflows.shell_command_parsing import (
    is_control_token,
    strip_shell_wrappers,
    tokenize,
)

if TYPE_CHECKING:
    from agentic_workflows.worktree_capacity import CapacitySnapshot

GIT_OPTIONS_WITH_VALUES = {
    "-C",
    "-c",
    "--config-env",
    "--exec-path",
    "--git-dir",
    "--namespace",
    "--super-prefix",
    "--work-tree",
}
READ_ONLY_REMOTE_ACTIONS = {"get-url", "show"}
FORCE_FLAGS = {"-f", "--force"}
GIT_LOCATION_OPTIONS = {"-C", "--git-dir", "--work-tree"}

# The only top-level git option that changes the process working directory, and
# so the only one a relative path operand resolves against. `--git-dir` and
# `--work-tree` name locations without ever chdir-ing.
GIT_CHDIR_OPTIONS = frozenset({"-C"})

# Branch namespaces the parallel-SDD workflow owns. Force-deleting one of these
# is its own cleanup; force-deleting anything else destroys someone else's work.
AGENT_BRANCH_PREFIXES = ("plan/", "sdd/")

# `git worktree` actions whose <path> operand decides authorization.
WORKTREE_PATH_ACTIONS = frozenset({"add", "remove"})

# The only `git worktree add` options carrying a separate value token, per
# `git worktree add -h`; attached forms (`-bfoo`) are skipped as flags anyway.
WORKTREE_OPTIONS_WITH_VALUES = frozenset({"-b", "-B", "--reason"})

# The four plumbing commands that write objects or move refs directly
# (REQ-028): `commit-tree` + `update-ref` lands a commit and repoints a branch
# without `git commit` ever running, defeating the commit block in every tier.
PLUMBING_SUBCOMMANDS = frozenset({"commit-tree", "hash-object", "mktree", "update-ref"})


def _short_flags_contain(args: list[str], letters: str) -> bool:
    """True if any short-option token (single dash, not '--') in args contains
    any of the given letters, whether alone or bundled with other short flags."""
    return any(
        arg.startswith("-")
        and not arg.startswith("--")
        and len(arg) > 1
        and any(letter in arg[1:] for letter in letters)
        for arg in args
    )


# The last resort of `_segment_is_dangerous_git`: blocked unless an earlier
# step allowed the invocation. `config` and `send-pack` survive every
# relaxation; `checkout`/`switch`/`update-index` are relaxed in an agent-owned
# worktree; `bisect` is UNVERIFIED, relaxed nowhere. All six must stay listed.
DEFAULT_BLOCKED_GIT_SUBCOMMANDS = {
    "bisect",
    "checkout",
    "config",
    "send-pack",
    "switch",
    "update-index",
}

# Derived, never re-stated: exactly git_state_scope's WORKTREE_LOCAL members.
AGENT_WORKTREE_RELAXED_SUBCOMMANDS = WORKTREE_LOCAL_SUBCOMMANDS


def is_git_dangerous_command(
    command: str,
    cwd: Path | None = None,
    *,
    rev_parse_head: Callable[[Path], str | None] | None = None,
    sha_resolves: Callable[[Path, str], bool] | None = None,
) -> bool:
    """Return True when a shell command contains a dangerous git invocation.

    `cwd` is the session's working directory. Every rule that depends on it
    resolves a `-C`/`--git-dir`/`--work-tree` override first, so all four agree
    on which checkout a command acts against: the `--no-verify` and `git commit`
    blocks (see `_acts_on_a_linked_worktree`), `git push` authorization (see
    `git_push_authorization`), and the agent-owned-worktree relaxation (see
    `is_agent_owned_worktree`). When `cwd` is omitted they all fail closed.

    `rev_parse_head`/`sha_resolves` are injected test seams for resolving the
    commit a push would send and establishing that a RECORDED SHA names a
    commit; when None the real `git rev-parse HEAD` / `git cat-file -e
    <sha>^{commit}` subprocesses run (see `git_push_authorization`).

    Capacity is deliberately not consulted here: the worktree-cap backstop
    denies on quota, not danger, and lives only in the hook seam
    (`build_git_danger_block_message`), so a full cap cannot reorder what this
    predicate calls dangerous."""

    return (
        find_dangerous_git_segment(
            command, cwd, rev_parse_head=rev_parse_head, sha_resolves=sha_resolves
        )
        is not None
    )


SegmentRefusalKind = Literal["matched", "unparseable", "unevaluable"]


class SegmentRefusal(NamedTuple):
    """A refusal and its reason kind. `segment` is the joined dangerous tokens
    for "matched"; otherwise nothing was judged and it carries the raw command.
    Post-Task-48 "unevaluable" is injected-seam-only: no natural input raises."""

    kind: SegmentRefusalKind
    segment: str


def find_dangerous_git_segment(
    command: str,
    cwd: Path | None = None,
    *,
    rev_parse_head: Callable[[Path], str | None] | None = None,
    sha_resolves: Callable[[Path, str], bool] | None = None,
) -> SegmentRefusal | None:
    """Return the first dangerous git command segment within a shell command,
    or None. The refusal names WHY (REQ-014): a matched pattern, a tokenize
    that could not resolve, or tokenized input evaluation could not judge —
    one `try` per step (evaluation raises `ValueError` too); all refuse."""

    try:
        segments = _iter_shell_segments(command)
    except ValueError:
        return SegmentRefusal("unparseable", command)

    try:
        tokens = _first_dangerous_segment_tokens(
            segments, cwd, rev_parse_head, sha_resolves
        )
    except ValueError:
        return SegmentRefusal("unevaluable", command)

    if tokens is None:
        return None
    return SegmentRefusal("matched", " ".join(tokens))


def build_git_danger_block_message(
    command: str,
    cwd: Path | None = None,
    *,
    rev_parse_head: Callable[[Path], str | None] | None = None,
    sha_resolves: Callable[[Path, str], bool] | None = None,
    capacity_probe: CapacityProbe | None = None,
) -> str | None:
    """Return a user-facing block reason for dangerous git commands. A blocked
    `push` returns its push-specific denial reason, a dangerous declared member
    names its classification's denial (`scope_denial_for`), an untokenizable
    command the parse-failure reason; every other blocked subcommand the
    generic message.

    A raw `git worktree add` against an agent-owned target additionally passes
    the capacity backstop: the shared capacity module is consulted and an
    at-cap (or undecidable-cap) creation is denied with a message pointing at
    the acquire script. `capacity_probe` injects that module's snapshot for
    tests; when None the real `worktree_capacity.capacity_snapshot` runs, so
    the hook and the script share one counting rule (REQ-010).

    Parsing runs in its own `try` rather than sharing one with the evaluation
    below, so the reason reported is decided by WHICH step failed, not guessed
    from the exception type: evaluation raises `ValueError` too (a path operand
    carrying an embedded NUL reaches `Path.resolve()`), and reporting that as a
    parse failure would be the same misreport in the opposite direction. Both
    still refuse — the `PreToolUse` hook treats any other exit code as a
    non-blocking error, so neither may escape."""

    try:
        segments = _iter_shell_segments(command)
    except ValueError as parse_error:
        return _unparseable_block_message(str(parse_error))

    try:
        tokens = _first_dangerous_segment_tokens(
            segments, cwd, rev_parse_head, sha_resolves
        )
    except ValueError:
        return _generic_block_message(command)

    if tokens is None:
        return _capacity_only_denial(segments, cwd, capacity_probe)

    git_command = _extract_git_command(tokens)
    if git_command is not None and git_command[0].lower() == "push":
        return push_denial_reason(
            git_command[1],
            _effective_checkout_location(tokens, cwd),
            rev_parse_head,
            sha_resolves,
        )

    if git_command is not None and git_command[0].lower() in PLUMBING_SUBCOMMANDS:
        return _plumbing_block_message(git_command[0].lower())

    if git_command is not None:
        subcommand = git_command[0].lower()
        denial = scope_denial_for(subcommand, git_command[1])
        checker = SUBCOMMAND_DANGER_CHECKS.get(subcommand)
        if denial is not None and (
            (checker is not None and checker(git_command[1]))
            or (checker is None and subcommand in DEFAULT_BLOCKED_GIT_SUBCOMMANDS)
        ):
            return denial

    return _generic_block_message(" ".join(tokens))


def _first_dangerous_segment_tokens(
    segments: list[list[str]],
    cwd: Path | None,
    rev_parse_head: Callable[[Path], str | None] | None,
    sha_resolves: Callable[[Path, str], bool] | None,
) -> list[str] | None:
    """Tokens of the first dangerous git segment, or None when none is
    dangerous. Takes already-tokenized segments so a caller's fail-closed
    handling of unparseable input wraps the tokenization call itself, never
    this evaluation."""

    for segment_tokens in segments:
        if _segment_is_dangerous_git(
            segment_tokens,
            cwd,
            rev_parse_head=rev_parse_head,
            sha_resolves=sha_resolves,
        ):
            return segment_tokens
    return None


def _generic_block_message(blocked_segment: str) -> str:
    return (
        "Blocked dangerous git command. Most git operations are allowed; only "
        "a specific set of destructive or irreversible patterns is blocked "
        "from agent sessions (see .agents/rules/block-git-mutations.md). "
        f"Blocked segment: {blocked_segment}"
    )


def _plumbing_block_message(subcommand: str) -> str:
    return (
        f"Blocked: git {subcommand} writes objects or moves refs directly, so "
        "it lands commits and repoints branches without the `git commit` block "
        "ever running. Use the ordinary porcelain commands instead "
        "(see .agents/rules/block-git-mutations.md)."
    )


# The complete set of `ValueError` messages `shlex.read_token` raises (CPython
# `Lib/shlex.py`, measured 2026-08-26); neither carries any input text.
PARSE_FAILURE_REASONS = {
    "No closing quotation": "a quote is opened and never closed",
    "No escaped character": "the command ends in a trailing backslash",
}

# Reached only if `shlex` gains a third message. Refusing is still correct and
# the wording stays true of any tokenization failure; the specific cause is
# deliberately given up — an unrecognized message is not proven input-free.
UNRECOGNIZED_PARSE_FAILURE = "its quoting could not be resolved"


def _unparseable_block_message(parse_error: str) -> str:
    """The refusal for a command tokenization could not resolve (REQ-190,
    REQ-191). It must not read as a decision about the command: nothing was
    inspected, so no git rule was consulted, and the deny-list document is not
    cited because citing it made this look like a git prohibition. The command
    is never echoed — arbitrary shell text can carry a credential."""

    reason = PARSE_FAILURE_REASONS.get(parse_error, UNRECOGNIZED_PARSE_FAILURE)
    return (
        f"Blocked: this command could not be parsed — {reason}. This is not a "
        "git prohibition and no git rule was consulted: the guard tokenizes a "
        "command before inspecting it, and refuses rather than guess when it "
        "cannot. Its text is not echoed back here. Workaround: if the command "
        "invokes no git operation, write its body to a file with the "
        "file-writing tool and run that file, instead of embedding it inline "
        "— an apostrophe left unpaired outside a heredoc body is enough to "
        "reach this."
    )


def _iter_shell_segments(command: str) -> list[list[str]]:
    tokens = tokenize(command)

    segments: list[list[str]] = []
    current: list[str] = []

    for token in tokens:
        if is_control_token(token):
            if current:
                segments.append(current)
                current = []
            continue
        current.append(token)

    if current:
        segments.append(current)

    return segments


def _action_is_unreadable(args: list[str]) -> bool:
    """True when a quoted empty argument sits where a caller reads the action."""
    return bool(args) and args[0] == ""


def _stash_is_dangerous(args: list[str]) -> bool:
    if _action_is_unreadable(args):
        return True
    return scope_denial_for("stash", args) is not None


def _first_path_operand(args: list[str]) -> str | None:
    """The first non-option token in `args`, skipping the value of any option
    in WORKTREE_OPTIONS_WITH_VALUES so `-b <new-branch>` is never mistaken for
    the path. None when there is no such token."""
    index = 0
    while index < len(args):
        token = args[index]
        if not token.startswith("-"):
            return token
        index += 2 if token in WORKTREE_OPTIONS_WITH_VALUES else 1
    return None


def _resolve_against(base: Path | None, target: Path) -> Path | None:
    """`target` made absolute against `base`. An absolute `target` ignores the
    base; a relative one with no base at all is unresolvable, so None."""
    if target.is_absolute():
        return target
    return None if base is None else base / target


def _chdir_base(tokens: list[str], cwd: Path | None) -> Path | None:
    """The directory git resolves a relative path operand against. Only `-C`
    moves it (repeated `-C` options compound relative to each other);
    `--git-dir` and `--work-tree` say where the repository and the working
    tree are but never change the process directory, so they leave this base
    alone — which is why they cannot be collapsed together with `-C` the way
    `_extract_git_location_override` collapses them for a different question.
    Only options before the subcommand count, matching git. Returns None (fail
    closed) when a relative `-C` has no `cwd` to resolve against."""
    command_tokens = strip_shell_wrappers(tokens)
    if not _head_is_git(command_tokens):
        return cwd

    base = cwd
    index = 1
    while index < len(command_tokens):
        # Every token this loop inspects is an option: it stops at the first
        # operand, and an option's own value is skipped without inspection.
        option = command_tokens[index]
        if not option.startswith("-"):
            break
        # Git accepts `-C <path>` only as two tokens; `-C=<path>` and `-C<path>`
        # are unknown options it dies on, so they never move the base.
        if option in GIT_CHDIR_OPTIONS and index + 1 < len(command_tokens):
            base = _resolve_against(base, Path(command_tokens[index + 1]))
            index += 2
            continue
        if option in GIT_OPTIONS_WITH_VALUES and index + 1 < len(command_tokens):
            index += 2
            continue
        index += 1

    return base


def _worktree_path_operand(
    action_args: list[str], tokens: list[str], cwd: Path | None
) -> Path | None:
    """The `<path>` operand of `git worktree add`/`remove` as an absolute path,
    or None when it cannot be established. A relative operand is resolved the
    way git itself would: against the `-C` directory when one is present, and
    against the session `cwd` otherwise (see `_chdir_base`) — this cannot
    authorize a target git would not act on, and the result still has to pass
    `is_agent_owned_worktree`. `~` stays literal: the shell expands it, and
    this guard sees the pre-expansion string, so a `~`-prefixed operand is denied."""
    operand = _first_path_operand(action_args)
    if operand is None:
        return None
    candidate = Path(operand)
    if candidate.is_absolute():
        return candidate
    return _resolve_against(_chdir_base(tokens, cwd), candidate)


def _worktree_is_dangerous(
    args: list[str], tokens: list[str], cwd: Path | None
) -> bool:
    """`add` and `remove --force` are permitted only against an agent-owned
    target — destroying a worktree this repo's agents created is their own
    intended cleanup. Non-force `remove` stays unrestricted (git refuses it on
    a dirty worktree, so it cannot destroy work); every other action (`list`,
    `prune`, `lock`, `unlock`, `move`) is unchanged. Fails closed on an
    undeterminable path operand."""
    if _action_is_unreadable(args):
        return True
    if not args or args[0] not in WORKTREE_PATH_ACTIONS:
        return False
    forced = bool(FORCE_FLAGS & set(args[1:])) or _short_flags_contain(args[1:], "f")
    if args[0] == "remove" and not forced:
        return False
    return not is_agent_owned_worktree(
        _worktree_path_operand(args[1:], tokens, cwd), cwd
    )


class CapacityProbe(Protocol):
    """The shared capacity authority as the hook seam consumes it: one
    snapshot of cap N and the current agent-worktree count for a checkout.
    Production resolves to `worktree_capacity.capacity_snapshot`; tests inject
    the same module's snapshots, so the hook and the acquire script can never
    grow divergent counting rules (REQ-010)."""

    def __call__(self, repo_root: Path, /) -> CapacitySnapshot: ...


ACQUIRE_SCRIPT = "scripts/worktree_acquire.py"


def _in_process_capacity_probe(repo_root: Path, /) -> CapacitySnapshot:
    """The production probe: the shared module, anchored on the same main
    checkout the ownership test anchored on, so the cap config resolves
    identically from any working directory. The import is function-local
    (measured 2026-09-17: cold `git_write_guard` 168ms, + capacity 178ms —
    a ~10ms marginal; only the `plan_run_state` half of that stack is
    already pulled through `git_push_authorization`, the pydantic half
    arrives with the capacity module itself) to keep the common deny-list
    pass exactly as light as before the backstop."""
    from agentic_workflows.worktree_capacity import (  # noqa: PLC0415 - measured lazy import, see docstring
        CONFIG_PATH,
        capacity_snapshot,
    )

    return capacity_snapshot(repo_root, config_path=repo_root / CONFIG_PATH)


def _capacity_full_block_message(capacity: CapacitySnapshot) -> str:
    return (
        "Blocked: the agent-worktree cap is full "
        f"({capacity.agent_worktree_count} of {capacity.max_concurrent} slots "
        "in use). Raw `git worktree add` may not create another worktree — "
        "acquire one through the script that owns creation: "
        f"`uv run python {ACQUIRE_SCRIPT} acquire --name <name> --branch <branch> --run <run>`."
    )


def _capacity_undecidable_block_message(error: Exception) -> str:
    """One denial for every way the capacity decision can fail to resolve:
    the capacity module's own `WorktreeCapacityError`, a probe that crashes
    (`OSError` from the listing subprocess, `RuntimeError` from a symlink
    loop, a bare `ValueError` from an embedded NUL reaching
    `Path.resolve()`), or an unresolvable main checkout. Whatever the
    failure, the message names it and points at the acquire script, which
    fails on the same input with exit 2."""
    return (
        "Blocked: the agent-worktree cap could not be decided, so a raw "
        "`git worktree add` is refused rather than allowed on an unknown "
        f"count. The capacity input failed: {error} Fix that input, or run "
        f"`uv run python {ACQUIRE_SCRIPT} acquire --name <name> --branch "
        "<branch> --run <run>`, which reports the same failure as exit 2."
    )


def _capacity_only_denial(
    segments: list[list[str]],
    cwd: Path | None,
    capacity_probe: CapacityProbe | None,
) -> str | None:
    """The backstop sweep for a command whose every segment evaluated safe:
    an agent-owned raw `git worktree add` is exactly such a command — no
    danger pattern matches it — so only the cap can still deny it. A segment
    that DID match a pattern is denied anyway and reported by its own rule,
    so this sweep runs solely on the benign path."""
    for segment_tokens in segments:
        git_command = _extract_git_command(segment_tokens)
        if git_command is None or git_command[0].lower() != "worktree":
            continue
        denial = _worktree_add_capacity_denial(
            git_command[1], segment_tokens, cwd, capacity_probe
        )
        if denial is not None:
            return denial
    return None


def _worktree_add_capacity_denial(
    args: list[str],
    tokens: list[str],
    cwd: Path | None,
    capacity_probe: CapacityProbe | None,
) -> str | None:
    """The capacity question for one `worktree` segment's action args, judged
    only for `add` against an agent-owned target — the one creation case the
    ownership rule authorizes. `remove` never reaches the probe: freeing a
    slot must stay possible at a full cap. Fail-closed on an undecidable
    count, on a probe that raises, or on an unresolvable main checkout,
    matching the capacity module's own posture: a guessed allow would
    silently unbound the cap, so the denial names the broken input and the
    script, which fails on the same input with exit 2."""
    if not args or args[0] != "add":
        return None
    if not is_agent_owned_worktree(_worktree_path_operand(args[1:], tokens, cwd), cwd):
        return None
    # The ownership test above anchors on the same `main_checkout_root(cwd)`
    # and only passes when it resolves, so None here means the checkout
    # structure was mutated between the two resolutions (a concurrent
    # process). Refusing costs one blocked command; allowing would silently
    # unbound the cap, so this is refused, never skipped.
    root = main_checkout_root(cwd)
    if root is None:
        return _capacity_undecidable_block_message(
            RuntimeError(
                "the session's main checkout root is unresolvable, so the "
                "capacity input cannot be anchored"
            )
        )

    from agentic_workflows.worktree_capacity import (  # noqa: PLC0415 - measured lazy import, see _in_process_capacity_probe
        WorktreeCapacityError,
    )

    probe = capacity_probe if capacity_probe is not None else _in_process_capacity_probe
    try:
        snapshot = probe(root)
    # `ValueError` keeps the docstring's "one denial for every failure" claim
    # true even for a shape this file does not produce today: bare
    # `ValueError` is what `Path.resolve()` raises on an embedded NUL, and
    # `WorktreeCapacityError` only narrows it.
    except (WorktreeCapacityError, OSError, RuntimeError, ValueError) as error:
        return _capacity_undecidable_block_message(error)
    if snapshot.acquire_allowed:
        return None
    return _capacity_full_block_message(snapshot)


def _reflog_is_dangerous(args: list[str]) -> bool:
    if _action_is_unreadable(args):
        return True
    return bool(args) and args[0] in {"delete", "expire"}


def _remote_is_dangerous(args: list[str]) -> bool:
    return not _is_read_only_remote(args)


def _is_force_delete(args: list[str]) -> bool:
    if _short_flags_contain(args, "D"):
        return True
    has_delete = bool({"-d", "--delete"} & set(args)) or _short_flags_contain(args, "d")
    has_force = bool(FORCE_FLAGS & set(args)) or _short_flags_contain(args, "f")
    return has_delete and has_force


def _is_agent_branch_name(name: str) -> bool:
    return any(name.startswith(prefix) for prefix in AGENT_BRANCH_PREFIXES)


def _branch_is_dangerous(args: list[str]) -> bool:
    """Force-deleting a branch is dangerous unless EVERY branch operand names
    one of this workflow's own branches. Operands are every token not starting
    with `-`; no option/value table is consulted, so a value-taking option can
    never hide a non-agent branch name. No operand at all fails closed."""
    if not _is_force_delete(args):
        return False
    operands = [arg for arg in args if not arg.startswith("-")]
    return not operands or not all(map(_is_agent_branch_name, operands))


def _tag_is_dangerous(args: list[str]) -> bool:
    denying_flags = FORCE_FLAGS | {"-d", "--delete"}
    return bool(denying_flags & set(args)) or _short_flags_contain(args, "fd")


def _reset_is_dangerous(args: list[str]) -> bool:
    return "--hard" in args


def _clean_is_dangerous(args: list[str]) -> bool:
    return not ({"-n", "--dry-run"} & set(args))


def _restore_is_dangerous(args: list[str]) -> bool:
    return not ({"--staged", "-S"} & set(args))


def _submodule_is_dangerous(args: list[str]) -> bool:
    return bool(FORCE_FLAGS & set(args)) or _short_flags_contain(args, "f")


def _gc_is_dangerous(args: list[str]) -> bool:
    return "--aggressive" in args or any(
        arg == "--prune" or arg.startswith("--prune=") for arg in args
    )


SUBCOMMAND_DANGER_CHECKS: dict[str, Callable[[list[str]], bool]] = {
    "stash": _stash_is_dangerous,
    "reflog": _reflog_is_dangerous,
    "remote": _remote_is_dangerous,
    "branch": _branch_is_dangerous,
    "tag": _tag_is_dangerous,
    "reset": _reset_is_dangerous,
    "clean": _clean_is_dangerous,
    "restore": _restore_is_dangerous,
    "submodule": _submodule_is_dangerous,
    "gc": _gc_is_dangerous,
}


def _segment_is_dangerous_git(
    tokens: list[str],
    cwd: Path | None,
    *,
    rev_parse_head: Callable[[Path], str | None] | None = None,
    sha_resolves: Callable[[Path, str], bool] | None = None,
) -> bool:
    git_command = _extract_git_command(tokens)
    if git_command is None:
        return False

    subcommand, args = git_command
    normalized = subcommand.lower()

    # An empty subcommand token is unreadable and git rejects it (measured);
    # plumbing is denied in EVERY tier: refs and objects are shared.
    if not normalized:
        return True
    if normalized in PLUMBING_SUBCOMMANDS:
        return True

    acts_on_linked_worktree = _acts_on_a_linked_worktree(tokens, cwd)

    if "--no-verify" in args and not acts_on_linked_worktree:
        return True

    if normalized == "commit" and not acts_on_linked_worktree:
        return True

    # `push` authorizes against `cwd` and the per-run state record, which the
    # cwd-less SUBCOMMAND_DANGER_CHECKS cannot see — as `commit` does above.
    if normalized == "push":
        return (
            push_denial_reason(
                args,
                _effective_checkout_location(tokens, cwd),
                rev_parse_head,
                sha_resolves,
            )
            != ""
        )

    # `worktree add`/`remove --force` authorize against the TARGET path, not
    # the invocation's own location, so they need `tokens`/`cwd` too.
    if normalized == "worktree":
        return _worktree_is_dangerous(args, tokens, cwd)

    # Inside an agent-owned worktree the single-working-tree deny list stops
    # applying. Membership is checked first so the filesystem walk runs only
    # for the six declared worktree-local subcommands; the rest stays blocked.
    if normalized in AGENT_WORKTREE_RELAXED_SUBCOMMANDS and is_agent_owned_worktree(
        enclosing_checkout_root(_effective_checkout_location(tokens, cwd)), cwd
    ):
        return False

    checker = SUBCOMMAND_DANGER_CHECKS.get(normalized)
    if checker is not None:
        return checker(args)

    return normalized in DEFAULT_BLOCKED_GIT_SUBCOMMANDS


def _head_is_git(command_tokens: list[str]) -> bool:
    """True when the head command is git itself, however spelled: matched on
    its basename, because `/usr/bin/git` is the same binary as `git`."""
    return bool(command_tokens) and PurePosixPath(command_tokens[0]).name == "git"


def _extract_git_command(tokens: list[str]) -> tuple[str, list[str]] | None:
    command_tokens = strip_shell_wrappers(tokens)
    if not _head_is_git(command_tokens):
        return None

    index = 1
    while index < len(command_tokens):
        token = command_tokens[index]
        if not token.startswith("-"):
            return token, command_tokens[index + 1 :]
        if token in GIT_OPTIONS_WITH_VALUES and index + 1 < len(command_tokens):
            index += 2
            continue
        if any(token.startswith(f"{option}=") for option in GIT_OPTIONS_WITH_VALUES):
            index += 1
            continue
        index += 1

    return None


def _extract_git_location_override(tokens: list[str]) -> str | None:
    """Return the path named by the last `-C`, `--git-dir`, or `--work-tree`
    top-level git option in `tokens`, if any (REQ-029). Reuses
    `_extract_git_command`'s recognition of these as options-with-values but
    captures the value instead of skipping it. Only options before the
    subcommand are considered, matching git."""
    command_tokens = strip_shell_wrappers(tokens)
    if not _head_is_git(command_tokens):
        return None

    override: str | None = None
    index = 1
    while index < len(command_tokens):
        token = command_tokens[index]
        if not token.startswith("-"):
            break
        if token in GIT_LOCATION_OPTIONS and index + 1 < len(command_tokens):
            override = command_tokens[index + 1]
            index += 2
            continue
        matched = next(
            (opt for opt in GIT_LOCATION_OPTIONS if token.startswith(f"{opt}=")),
            None,
        )
        if matched is not None:
            override = token[len(matched) + 1 :]
            index += 1
            continue
        if token in GIT_OPTIONS_WITH_VALUES and index + 1 < len(command_tokens):
            index += 2
            continue
        if any(token.startswith(f"{option}=") for option in GIT_OPTIONS_WITH_VALUES):
            index += 1
            continue
        index += 1

    return override


def _effective_checkout_location(tokens: list[str], cwd: Path | None) -> Path | None:
    """Resolve the effective checkout location for a git invocation (REQ-029):
    a `-C`/`--git-dir`/`--work-tree` value if present (resolved against `cwd`
    when relative), else raw `cwd` unchanged."""
    override = _extract_git_location_override(tokens)
    if override is None:
        return cwd

    override_path = Path(override)
    if not override_path.is_absolute() and cwd is not None:
        override_path = cwd / override_path
    return override_path


def _acts_on_a_linked_worktree(tokens: list[str], cwd: Path | None) -> bool:
    """True when the checkout this invocation actually operates against is a
    linked worktree rather than the main checkout. Both rules that turn on
    that distinction — the blanket `--no-verify` block and the `git commit`
    block — share this one predicate, so they can never disagree about which
    checkout a command acts on. `-C`/`--git-dir`/`--work-tree` are resolved
    first: raw `cwd` would judge `git -C <worktree> ...` against the session's
    own directory, and equally let `git -C <main> ...` pass from a worktree.
    Fails closed (False, i.e. "not a worktree", so the caller blocks) whenever
    the effective checkout location can't be determined at all."""
    return cwd_is_linked_worktree(_effective_checkout_location(tokens, cwd))


def _is_read_only_remote(args: list[str]) -> bool:
    if not args:
        return True

    action = args[0]
    if action in READ_ONLY_REMOTE_ACTIONS:
        return True

    return all(arg in {"-v", "--verbose"} for arg in args)
