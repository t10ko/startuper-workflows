import pytest

from agentic_workflows.shell_command_parsing import (
    is_control_token,
    strip_shell_wrappers,
    tokenize,
)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git status", ["git", "status"]),
        ("git status && git diff", ["git", "status", "&&", "git", "diff"]),
        ("rg foo | grep bar", ["rg", "foo", "|", "grep", "bar"]),
        ("echo 'a; b' && echo done", ["echo", "a; b", "&&", "echo", "done"]),
        (
            "grep foo file1 file2 && echo done",
            ["grep", "foo", "file1", "file2", "&&", "echo", "done"],
        ),
    ],
)
def test_tokenize_splits_words_and_control_tokens(
    command: str, expected: list[str]
) -> None:
    assert tokenize(command) == expected


def test_tokenize_treats_unquoted_newlines_as_statement_separators() -> None:
    assert tokenize("git status\ngit diff") == ["git", "status", ";", "git", "diff"]


def test_tokenize_raises_value_error_on_unbalanced_quotes() -> None:
    with pytest.raises(ValueError, match="No closing quotation"):
        tokenize("echo 'unterminated")


def test_tokenize_empty_command_returns_no_tokens() -> None:
    assert tokenize("   ") == []


@pytest.mark.parametrize(
    ("token", "expected"),
    [
        ("&&", True),
        ("||", True),
        (";", True),
        ("|", True),
        ("&", True),
        ("(", True),
        (")", True),
        ("git", False),
        ("--force", False),
        # An empty argument is a WORD the shell passes through, not punctuation.
        # `set("").issubset(...)` is vacuously true, so this returned True and
        # every guard built on this stream ended its segment at a `''` operand:
        # measured, `git stash '' drop`, `git reflog '' delete`, `git gc ''
        # --prune=now` and `git remote '' set-url` each went from BLOCKED to
        # ALLOWED. git itself rejects all four, so no git bypass was live, but
        # `sed -i '' -e ... <file>` is a real command whose file operand the
        # split hid outright.
        ("", False),
    ],
)
def test_is_control_token(token: str, expected: bool) -> None:
    assert is_control_token(token) is expected


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        (["git", "status"], ["git", "status"]),
        (["FOO=1", "git", "status"], ["git", "status"]),
        (["env", "FOO=1", "BAR=2", "git", "status"], ["git", "status"]),
        (["sudo", "-u", "root", "git", "status"], ["git", "status"]),
        (["nohup", "git", "status"], ["git", "status"]),
        (["time", "git", "status"], ["git", "status"]),
        # A wrapper is a program like any other, so its path spelling names the
        # same one. Measured against the live guard before this: `/usr/bin/env
        # git reset --hard` and `/usr/bin/sudo git reset --hard` were ALLOWED
        # from the main checkout while their bare spellings were BLOCKED.
        (["/usr/bin/env", "git", "status"], ["git", "status"]),
        (["/usr/bin/sudo", "git", "status"], ["git", "status"]),
        (["/bin/nohup", "git", "status"], ["git", "status"]),
        # `env` takes options of its own, and the assignments-only skip left
        # `-i` standing as the command name with everything behind it hidden.
        (["env", "-i", "git", "status"], ["git", "status"]),
        (["env", "-u", "FOO", "git", "status"], ["git", "status"]),
        (["env", "--unset=FOO", "git", "status"], ["git", "status"]),
        (["env", "-i", "-u", "FOO", "BAR=1", "git", "status"], ["git", "status"]),
        (["env", "--", "git", "status"], ["git", "status"]),
        # A wrapper that takes a command as its operand hid every git
        # invocation behind it. Measured against the live guard before this,
        # from the main checkout: `timeout 5 git reset --hard`, `xargs git
        # reset --hard`, `exec git reset --hard`, `nice git reset --hard`,
        # `setsid`/`stdbuf`/`ionice` spellings, and the option-bearing forms
        # of the wrappers already listed (`time -p git reset --hard`,
        # `command -p git reset --hard`) were all ALLOWED.
        (["timeout", "5", "git", "status"], ["git", "status"]),
        (["timeout", "-s", "KILL", "5", "git", "status"], ["git", "status"]),
        (["timeout", "--signal=KILL", "5m", "git", "status"], ["git", "status"]),
        (["timeout", "-k", "1", "5", "git", "status"], ["git", "status"]),
        (["xargs", "git", "status"], ["git", "status"]),
        (["xargs", "-n", "1", "git", "status"], ["git", "status"]),
        (["xargs", "-0", "-I", "{}", "git", "status"], ["git", "status"]),
        (["exec", "git", "status"], ["git", "status"]),
        (["exec", "-a", "name", "git", "status"], ["git", "status"]),
        (["nice", "git", "status"], ["git", "status"]),
        (["nice", "-n", "10", "git", "status"], ["git", "status"]),
        (["nice", "-10", "git", "status"], ["git", "status"]),
        (["setsid", "git", "status"], ["git", "status"]),
        (["stdbuf", "-o0", "git", "status"], ["git", "status"]),
        (["stdbuf", "-o", "0", "git", "status"], ["git", "status"]),
        (["ionice", "-c3", "git", "status"], ["git", "status"]),
        (["ionice", "-c", "3", "git", "status"], ["git", "status"]),
        (["time", "-p", "git", "status"], ["git", "status"]),
        (["time", "-o", "/tmp/t", "git", "status"], ["git", "status"]),
        (["command", "-p", "git", "status"], ["git", "status"]),
        (["/usr/bin/timeout", "5", "git", "status"], ["git", "status"]),
        (["timeout", "5", "nice", "-n", "5", "git", "status"], ["git", "status"]),
        # `command -v`/`-V` PRINT where a program lives instead of running it,
        # so nothing behind them is an invocation to judge; stripping there
        # would block a lookup that never executes.
        (["command", "-v", "git"], ["command", "-v", "git"]),
        (["command", "-V", "grep"], ["command", "-V", "grep"]),
        # A wrapper with nothing behind it leaves no command to reach.
        (["timeout", "5"], []),
    ],
)
def test_strip_shell_wrappers(tokens: list[str], expected: list[str]) -> None:
    assert strip_shell_wrappers(tokens) == expected


def test_tokenize_drops_a_quoted_heredoc_body() -> None:
    """A quoted delimiter makes the body literal text the shell never expands.

    Reading it as shell is what turned an apostrophe in prose into
    `ValueError: No closing quotation`, which every guard then fails closed
    on -- blocking a command with no git in it at all.
    """
    command = "cat <<'EOF' > notes.md\nDon't pass `--no-verify`.\nEOF\n"

    assert tokenize(command) == ["cat", "<<EOF", ">", "notes.md", ";"]


def test_tokenize_drops_an_unquoted_heredoc_body_with_nothing_to_expand() -> None:
    command = "cat <<EOF > notes.md\nDon't pass --no-verify.\nEOF\n"

    assert tokenize(command) == ["cat", "<<EOF", ">", "notes.md", ";"]


@pytest.mark.parametrize(
    "body",
    ["$(git reset --hard)", "`git reset --hard`", "${x} and $(git clean -fdx)"],
)
def test_tokenize_keeps_an_unquoted_heredoc_body_that_the_shell_expands(
    body: str,
) -> None:
    """An unquoted delimiter is not data: the shell runs substitutions inside
    it, so dropping the body would hide a real command from every guard."""
    command = f"cat <<EOF > notes.md\n{body}\nEOF\n"

    assert any("git" in token for token in tokenize(command))


def test_tokenize_keeps_an_unterminated_heredoc_body() -> None:
    """No terminator line means no measurable body end, so nothing is dropped
    -- the fail-closed direction, leaving the pre-existing behaviour."""
    command = "cat <<'EOF' > notes.md\ngit reset --hard\n"

    assert "git" in tokenize(command)


def test_tokenize_keeps_commands_after_the_heredoc_terminator() -> None:
    command = "cat <<'EOF' > notes.md\nprose\nEOF\ngit reset --hard"

    assert tokenize(command) == [
        "cat",
        "<<EOF",
        ">",
        "notes.md",
        ";",
        "git",
        "reset",
        "--hard",
    ]


def test_tokenize_drops_a_dash_heredoc_body_with_a_tab_indented_terminator() -> None:
    command = "cat <<-EOF > notes.md\n\tprose\n\tEOF\ngit status"

    assert tokenize(command) == ["cat", "<<-EOF", ">", "notes.md", ";", "git", "status"]


def test_tokenize_leaves_a_here_string_alone() -> None:
    """`<<<` is a here-string: one word on the same line, no body to drop."""
    assert tokenize("grep foo <<<bar") == ["grep", "foo", "<<<bar"]


def test_tokenize_ignores_a_heredoc_operator_inside_quotes() -> None:
    assert tokenize("echo '<<EOF'\ngit status") == [
        "echo",
        "<<EOF",
        ";",
        "git",
        "status",
    ]


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("echo `git reset --hard`", ["echo", ";", "git", "reset", "--hard"]),
        ('echo "`git status`"', ["echo", "", ";", "git", "status"]),
        ('echo "$(git status)"', ["echo", "", ";", "git", "status"]),
        ("x=`git status` echo hi", ["x=", "echo", "hi", ";", "git", "status"]),
        (
            "echo $(echo $(git status))",
            ["echo", ";", "echo", ";", "git", "status"],
        ),
    ],
)
def test_tokenize_exposes_a_substitution_the_shell_would_run(
    command: str, expected: list[str]
) -> None:
    """A command substitution is a command, and must tokenize as one.

    `shlex` has no notion of substitution. `$(` splits only because `(` is a
    punctuation character, and only outside quotes; a backtick splits nothing
    at all. Measured against the tokenizer before this change: ``echo `git
    reset --hard` `` yielded ``['echo', '`git', 'reset', '--hard`']`` -- no
    token equal to `git` anywhere, so every deny-list built on this stream
    read straight past it.
    """
    assert tokenize(command) == expected


@pytest.mark.parametrize(
    "command",
    [
        "echo '`git reset --hard`'",
        "echo '$(git reset --hard)'",
        r"echo \`git reset --hard\`",
    ],
)
def test_tokenize_leaves_text_the_shell_never_runs_as_one_word(command: str) -> None:
    """Single quotes and a backslash make a substitution literal, not a command.

    Exposing these would block a command that never happens, which is the
    failure mode opposite to the one above and no more acceptable.
    """
    assert "git" not in tokenize(command)
