"""Quote-aware shell command tokenization shared by PreToolUse guard hooks.

Extracted from `git_write_guard` once a second guard (`grep_search_guard`)
needed the same parsing: control-token splitting, wrapper stripping.
"""

from __future__ import annotations

import re
import shlex
from pathlib import PurePosixPath
from typing import NamedTuple

CONTROL_TOKENS = frozenset({"&&", "||", ";", "|", "&", "(", ")"})
ASSIGNMENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
HEREDOC_DELIMITER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
#: What may follow a heredoc delimiter. `)` is absent on purpose: it is what
#: keeps `$((x << y))` from reading as a heredoc named `y`.
HEREDOC_WORD_ENDINGS = frozenset({" ", "\t", "\n", ">", "<", "|", "&", ";"})
#: The only two forms that make a shell run a command while expanding a
#: heredoc body. `$(` also covers `$((`, conservatively.
EXPANSION_MARKERS = ("`", "$(")


class WrapperSpec(NamedTuple):
    """How to walk past one wrapper program to the command it runs.

    `options_with_values` are the wrapper's own options that consume a
    separate following token; every other leading `-` token is skipped on its
    own. `operands` is how many positional tokens the wrapper eats before the
    command name (only `timeout`, whose DURATION comes first, has any).
    `non_executing_options` name the forms where the wrapper INSPECTS a
    program instead of running it, so nothing behind them is an invocation at
    all and the token stream must be left exactly as it stands."""

    options_with_values: frozenset[str] = frozenset()
    operands: int = 0
    non_executing_options: frozenset[str] = frozenset()


#: Every wrapper whose operand is another command to run, with the arguments
#: of its own that stand between it and that command. A wrapper word left out
#: of this table hides everything behind it from every guard reading this
#: stream: measured from the main checkout before this table existed,
#: `timeout 5 git reset --hard`, `xargs git reset --hard`, `exec git reset
#: --hard`, `nice git reset --hard`, the `setsid`/`stdbuf`/`ionice` spellings,
#: and the option-bearing forms of the four wrappers already recognised
#: (`time -p ...`, `command -p ...`) were ALL allowed.
SHELL_WRAPPERS: dict[str, WrapperSpec] = {
    "builtin": WrapperSpec(),
    "command": WrapperSpec(non_executing_options=frozenset({"-v", "-V"})),
    "exec": WrapperSpec(options_with_values=frozenset({"-a"})),
    "ionice": WrapperSpec(
        options_with_values=frozenset(
            {"-c", "-n", "-p", "-P", "--class", "--classdata", "--pid", "--pgid"}
        )
    ),
    "nice": WrapperSpec(options_with_values=frozenset({"-n", "--adjustment"})),
    "nohup": WrapperSpec(),
    "setsid": WrapperSpec(),
    "stdbuf": WrapperSpec(
        options_with_values=frozenset(
            {"-i", "-o", "-e", "--input", "--output", "--error"}
        )
    ),
    "time": WrapperSpec(
        options_with_values=frozenset({"-f", "--format", "-o", "--output"})
    ),
    "timeout": WrapperSpec(
        options_with_values=frozenset({"-s", "--signal", "-k", "--kill-after"}),
        operands=1,
    ),
    "xargs": WrapperSpec(
        options_with_values=frozenset(
            {
                "-a",
                "--arg-file",
                "-d",
                "--delimiter",
                "-E",
                "-I",
                "-i",
                "--replace",
                "-L",
                "-l",
                "--max-lines",
                "-n",
                "--max-args",
                "-P",
                "--max-procs",
                "-s",
                "--max-chars",
            }
        )
    ),
}
#: `env` options that consume a separate value token. `-i`/`--ignore-environment`
#: and the other valueless ones need no entry: any leading `-` token is skipped,
#: and only these additionally swallow the token after them.
ENV_OPTIONS_WITH_VALUES = frozenset(
    {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}
)
SUDO_OPTIONS_WITH_VALUES = frozenset(
    {
        "-C",
        "-g",
        "-h",
        "-p",
        "-u",
        "--chdir",
        "--group",
        "--host",
        "--other-user",
        "--prompt",
        "--user",
    }
)


def is_control_token(token: str) -> bool:
    """True for shell control-flow punctuation (pipes, sequencing, subshells).

    The emptiness check is load-bearing, not defensive: `set("")` is a subset of
    every set, so an empty token -- what a shell passes through for a quoted
    `''` argument -- used to read as punctuation and end the segment a guard was
    inspecting. `sed -i '' -e ... <file>` is the everyday command that produces
    one, and its file operand vanished from the stream entirely.
    """
    if not token:
        return False
    return token in CONTROL_TOKENS or set(token).issubset({"&", ";", "|", "(", ")"})


def replace_unquoted_newlines(command: str) -> str:
    """Replace newlines outside quoted strings with ';' so multi-line shell
    input segments the same way as semicolon-separated commands."""

    result: list[str] = []
    quote_char: str | None = None
    escaped = False
    for char in command:
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == "\\" and quote_char != "'":
            result.append(char)
            escaped = True
            continue
        if quote_char is None:
            if char in "\"'":
                quote_char = char
            elif char == "\n":
                result.append(";")
                continue
        elif char == quote_char:
            quote_char = None
        result.append(char)
    return "".join(result)


class _HeredocOpening(NamedTuple):
    """One heredoc redirection found on a line, ready to have its body cut."""

    delimiter: str
    quoted: bool
    allow_indent: bool
    operator_end: int


def _read_heredoc_opening(command: str, index: int) -> _HeredocOpening | None:
    """Parse a heredoc redirection starting at `<<`, or None if it is not one.

    Deliberately narrow: the delimiter must be a bare identifier, optionally
    wrapped in one pair of quotes or preceded by a backslash, and the next
    character must end a word. `$((x << y))` and `<<"EO"F` both fail that and
    are left alone -- the fail-closed direction, since not recognising a
    heredoc only preserves the pre-existing behaviour.
    """
    cursor = index + 2
    allow_indent = command.startswith("-", cursor)
    if allow_indent:
        cursor += 1
    while cursor < len(command) and command[cursor] in " \t":
        cursor += 1

    quoted = False
    if cursor < len(command) and command[cursor] == "\\":
        quoted = True
        cursor += 1
    quote_char = ""
    if cursor < len(command) and command[cursor] in "\"'":
        quoted = True
        quote_char = command[cursor]
        cursor += 1

    match = HEREDOC_DELIMITER_PATTERN.match(command, cursor)
    if match is None:
        return None
    cursor = match.end()

    if quote_char:
        if not command.startswith(quote_char, cursor):
            return None
        cursor += 1
    if cursor < len(command) and command[cursor] not in HEREDOC_WORD_ENDINGS:
        return None

    return _HeredocOpening(match.group(), quoted, allow_indent, cursor)


def _next_heredoc(command: str) -> _HeredocOpening | None:
    """First unquoted heredoc redirection in `command`, `<<<` excluded."""

    quote_char: str | None = None
    escaped = False
    index = 0
    while index < len(command):
        char = command[index]
        if escaped:
            escaped = False
        elif char == "\\" and quote_char != "'":
            escaped = True
        elif quote_char is not None:
            if char == quote_char:
                quote_char = None
        elif char in "\"'":
            quote_char = char
        elif command.startswith("<<<", index):
            index += 3
            continue
        elif command.startswith("<<", index):
            opening = _read_heredoc_opening(command, index)
            if opening is not None:
                return opening
            index += 2
            continue
        index += 1
    return None


def _terminator_span(
    command: str, body_start: int, opening: _HeredocOpening
) -> tuple[int, int] | None:
    """Half-open span of the terminator line, or None when there is none."""

    position = body_start
    while position <= len(command):
        line_end = command.find("\n", position)
        line = command[position:] if line_end < 0 else command[position:line_end]
        candidate = line.lstrip("\t") if opening.allow_indent else line
        if candidate == opening.delimiter:
            return (position, len(command) if line_end < 0 else line_end + 1)
        if line_end < 0:
            return None
        position = line_end + 1
    return None


def strip_heredoc_bodies(command: str) -> str:
    """Remove heredoc bodies so a guard reads them as data, not as shell.

    A heredoc body is stdin content, never a command, so tokenizing it is
    wrong twice over: an apostrophe in prose raises `ValueError: No closing
    quotation`, which every caller fails closed on, and a word in prose can
    read as a flag the deny-list rejects.

    Two cases keep their body, both fail-closed. An **unterminated** heredoc
    has no measurable end. An **unquoted** delimiter means the shell expands
    the body, so a command substitution inside it really does run -- dropping
    that would hide a real command from the deny-list, which is strictly
    worse than the friction this removes.
    """
    kept: list[str] = []
    remaining = command
    while True:
        opening = _next_heredoc(remaining)
        if opening is None:
            kept.append(remaining)
            return "".join(kept)

        line_break = remaining.find("\n", opening.operator_end)
        if line_break < 0:
            kept.append(remaining)
            return "".join(kept)
        body_start = line_break + 1

        span = _terminator_span(remaining, body_start, opening)
        if span is None:
            kept.append(remaining)
            return "".join(kept)

        body = remaining[body_start : span[0]]
        if not opening.quoted and any(marker in body for marker in EXPANSION_MARKERS):
            kept.append(remaining)
            return "".join(kept)

        kept.append(remaining[:body_start])
        remaining = remaining[span[1] :]


def _closing_backtick(command: str, start: int) -> int:
    """Index of the backtick ending a substitution opened before `start`."""
    index = start
    quote: str | None = None
    while index < len(command):
        char = command[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if quote is not None:
            quote = None if char == quote else quote
        elif char in "\"'":
            quote = char
        elif char == "`":
            return index
        index += 1
    return -1


def _closing_paren(command: str, start: int) -> int:
    """Index of the `)` closing a `$(` opened before `start`, nesting aware."""
    index = start
    depth = 1
    quote: str | None = None
    while index < len(command):
        char = command[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if quote is not None:
            quote = None if char == quote else quote
        elif char in "\"'":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return -1


def _split_command_substitutions(command: str) -> tuple[str, list[str]]:
    """The command with its substitutions cut out, plus each cut-out body."""
    outer: list[str] = []
    bodies: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(command):
        char = command[index]
        if quote == "'":
            outer.append(char)
            if char == "'":
                quote = None
            index += 1
            continue
        if char == "\\" and index + 1 < len(command):
            outer.append(command[index : index + 2])
            index += 2
            continue
        if quote is None and char == "'":
            quote = "'"
            outer.append(char)
            index += 1
            continue
        if char == '"':
            quote = None if quote == '"' else '"'
            outer.append(char)
            index += 1
            continue
        opened = 1 if char == "`" else 2 if command.startswith("$(", index) else 0
        if opened:
            end = (
                _closing_backtick(command, index + 1)
                if opened == 1
                else _closing_paren(command, index + 2)
            )
            if end < 0:
                # Unterminated: not a shell command at all. Leaving the rest
                # verbatim keeps whatever the tokenizer made of it before.
                outer.append(command[index:])
                break
            inner, nested = _split_command_substitutions(command[index + opened : end])
            bodies.append(inner)
            bodies.extend(nested)
            index = end + 1
            continue
        outer.append(char)
        index += 1
    return "".join(outer), bodies


def lift_command_substitutions(command: str) -> str:
    """Move every substitution the shell would run into its own segment.

    `shlex` has no notion of command substitution. `$(` splits only because
    `(` is a punctuation character, and only outside quotes; a backtick splits
    nothing at all. Measured: ``echo `git reset --hard` `` tokenized to
    ``['echo', '`git', 'reset', '--hard`']`` -- no token equal to `git`, so
    every deny-list built on this stream read straight past a command that
    really runs. Three of the four executing forms were invisible; only bare
    `$(...)` was not.

    Each body is appended as its own `;`-separated segment and removed from
    where it stood, so the outer command keeps its own words and their order
    and nothing that was blocked before stops being blocked.

    Single-quoted text and a backslash-escaped backtick are left exactly as
    they were: the shell does not run those, and exposing them would block a
    command that never happens.
    """
    outer, bodies = _split_command_substitutions(command)
    if not bodies:
        return command
    return " ; ".join([outer, *bodies])


def tokenize(command: str) -> list[str]:
    """Quote- and punctuation-aware tokenization of a shell command line.

    Returns a flat stream mixing plain word tokens with control tokens (see
    `is_control_token`) in original order. Raises `ValueError` on unbalanced
    quoting, mirroring `shlex`.
    """

    if not command.strip():
        return []

    normalized = replace_unquoted_newlines(
        lift_command_substitutions(strip_heredoc_bodies(command))
    )
    lexer = shlex.shlex(normalized, posix=True, punctuation_chars=";&|()")
    lexer.commenters = ""
    lexer.whitespace_split = True
    return list(lexer)


def _skip_env_arguments(tokens: list[str], index: int) -> int:
    """Index of the command `env` runs, past its own options and assignments.

    `env -i cp ...` and `env -u FOO cp ...` are the everyday spellings that
    stopped the old assignments-only skip dead, leaving `-i` as the command
    name and hiding everything behind it from every guard reading this stream.
    """

    while index < len(tokens):
        argument = tokens[index]
        if argument == "--":
            return index + 1
        if ASSIGNMENT_PATTERN.match(argument):
            index += 1
            continue
        if not argument.startswith("-") or argument == "-":
            return index
        option, separator, _ = argument.partition("=")
        index += 1
        takes_a_separate_value = (
            option in ENV_OPTIONS_WITH_VALUES and not separator and index < len(tokens)
        )
        if takes_a_separate_value:
            index += 1
    return index


def _skip_wrapper_arguments(
    tokens: list[str], index: int, spec: WrapperSpec
) -> int | None:
    """Index of the command this wrapper runs, past its own options and any
    positional operands it eats first. None when the wrapper does not run the
    command at all (a `non_executing_options` form), which tells the caller to
    leave the token stream standing where the wrapper starts."""

    while index < len(tokens):
        option = tokens[index]
        if option == "--":
            index += 1
            break
        if not option.startswith("-") or option == "-":
            break
        if option in spec.non_executing_options:
            return None
        index += 1
        if option in spec.options_with_values and index < len(tokens):
            index += 1

    return min(index + spec.operands, len(tokens))


def strip_shell_wrappers(tokens: list[str]) -> list[str]:
    """Strip leading env-var assignments, `env`, `sudo`, and every wrapper word
    in `SHELL_WRAPPERS` -- together with that wrapper's own options and
    operands -- to reach the real command.

    Each wrapper is matched on its **basename**, because a wrapper is a
    program like any other and `/usr/bin/env` names the same one as `env`.
    Measured against the live git guard before this: `/usr/bin/env git reset
    --hard` and `/usr/bin/sudo git reset --hard` were both ALLOWED from the
    main checkout while their unqualified spellings were BLOCKED.
    """

    index = 0

    while index < len(tokens):
        part = tokens[index]
        name = PurePosixPath(part).name

        if ASSIGNMENT_PATTERN.match(part):
            index += 1
            continue

        if name == "env":
            index = _skip_env_arguments(tokens, index + 1)
            continue

        spec = SHELL_WRAPPERS.get(name)
        if spec is not None:
            past_wrapper = _skip_wrapper_arguments(tokens, index + 1, spec)
            if past_wrapper is None:
                break
            index = past_wrapper
            continue

        if name == "sudo":
            index += 1
            while index < len(tokens) and tokens[index].startswith("-"):
                option = tokens[index]
                index += 1
                if option in SUDO_OPTIONS_WITH_VALUES and index < len(tokens):
                    index += 1
            continue

        break

    return tokens[index:]
