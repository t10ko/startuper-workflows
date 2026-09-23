"""Which file paths a shell command would write, as far as that is decidable.

`git_write_guard` inspects `git` invocations and nothing else, so every other
command's file operands pass through it unread — measured on this tree, all of
`printf > <record>`, `sed -i`, `tee`, `cp`, `ln`, `mv`, `dd of=` and a plain
`>` redirect reach `.git/**` or a plan-run authorization record with nothing to
stop them. This module extracts the write targets it can recognize so a guard
can hold them against a protected path class. It decides **nothing** about
whether a target is allowed; that is the caller's judgment.

Paths come back **as written**, never resolved. The protected-path predicates
in `git_internals_edit_guard` test the written form first and anchor the rest
against the working directory the tool layer reported, so resolving here would
duplicate that logic in a second place with no working directory to do it with.

## A recognizer, not a decision procedure

What a shell command writes is undecidable in general: a target can be computed
at runtime, read from a variable, or produced inside an interpreter this module
never looks into. Everything below is therefore stated as a *table of shapes*,
and the shapes outside it are enumerated rather than left implied. A partial
parser presented as complete gives false confidence, which is the failure
`.agents/rules/memory-consent.md` already records for a guard of this kind.

### Recognized

| Shape | Target |
| --- | --- |
| `>`, `>>`, `N>`, `N>>`, `>` + `|`, `&>`, `>&<word>`, `N<>` | the redirect operand, split or glued (`x>f`) |
| `tee [-a] FILE...` | every file operand |
| `sed -i` | every file operand, both GNU (`-i[SUF]`) and BSD (`-i SUF`) spellings |
| `cp`, `install` | the destination, or `-t`/`--target-directory`, or every operand under `install -d` |
| `mv` | the destination **and** every source — moving a protected file away disables what reads it |
| `ln`, `ln -s` | the destination **and** every source — a link makes its source writable through a second name, which is the hard-link bypass this repository has already demonstrated live |
| `dd of=FILE` | the `of=` operand |
| `rm`, `unlink`, `truncate`, `touch`, `chmod`, `chown`, `mkdir` | every operand — deleting, emptying or unsetting the execute bit on `.git/hooks/pre-commit` defeats the commit gate as surely as rewriting it |
| `curl -o`, `wget -O`/`-o`/`-P` | the named output operand — fetching a payload straight onto a protected path |
| `cd DIR` | not a target; DIR is carried as a prefix onto later relative targets |

Every option value above is read in all three spellings a shell accepts —
`-o VALUE`, `--output=VALUE`, and glued `-oVALUE` (bundles included, split at
the first value-taking letter, which is getopt's own rule). Glued is the
*standard* spelling for the two fetchers, so reading only the other two made
the row above describe coverage that was not there.

Every command name is read as a **basename**, and so is every wrapper
(`env`, `sudo`, `nohup`, `time`, `command`, `builtin`) — `/usr/bin/env cp` is
`cp`, and `env -i`/`env -u FOO` are read past to reach it. A segment whose
first word is not in the table is then scanned word by word for one that is,
because an ordinary command in front of a recognized one (`timeout 5 cp ...`,
`nice cp ...`, `exec cp ...`) is not a shell construct any enumeration below
reaches; nor is a brace group, an `if` body, or a loop body. That deeper
reading is a guess (`pip install a b` is not GNU `install`), so it reports
targets and never doubt.

A file-descriptor duplication (`2>&1`, `>&-`) is not a write and yields no
target: reading it as one would refuse every `make verify 2>&1` in the repo.

### NOT recognized — the enumeration is part of the deliverable

1. **Any interpreter writing through its own runtime.** `python -c`, `uv run
   python script.py`, `perl -e`, `node -e`, `awk`, a `Makefile` target, a
   compiled binary. The command string carries no operand naming what gets
   written, and nothing static can recover one. This is the structural hole,
   and no growth of the table above closes it. One narrow case falls out
   anyway: `bash -c "... > <path>"` and `eval "... > <path>"` put a literal
   redirect inside a single token, which is reported undecidable under
   `DoubtKind.UNCERTAIN_WRITE` — the same word could be `rg -n 'x > <path>'`
   or a commit message, and whitespace beside the `>` is the only signal,
   which says the operator was quoted and says nothing about what quoted it.
   That doubt carries its own kind precisely because a caller's policy has to
   differ there: refusing it costs every command whose *data* contains a `>`,
   and buys nothing, since the same `bash -c` calling `python -c` is invisible
   again. Claiming the search reads as a write is the other error — a false
   refusal on an everyday command and a false statement about what it does.
2. **Writing commands outside the table.** `patch`, `rsync`, `tar -x`, `unzip`,
   `split`, `sort -o`, `gzip`, `git apply`, `git checkout -- <path>`, and any
   editor. Bulk writers are the worst of these: what `tar -x` or `patch` writes
   lives in the archive or the diff, not in the command, so recognizing the
   command name would not recover a target anyway. The table is data-driven and
   a command whose destination IS an operand costs a few lines to add. Absence
   here means **unrecognized**, never **safe**.
3. **Runtime-determined targets.** A variable (`> "$T"`), a glob, a brace
   expansion, or a command substitution as the operand. These are reported as
   *undecidable* under `DoubtKind.UNREADABLE_TARGET` rather than skipped, so a
   caller can fail closed on them — including the two shapes a lifted command
   substitution leaves behind: an empty operand token (it was quoted) and a
   shape missing an operand it requires (it ended the segment).
   **One residual, measured:** a substitution *between* two words leaves no
   trace at all. `curl -o $(echo <path>) <url>` closes the gap it left, `-o`
   ends up beside the URL, and nothing in what remains says a token stood
   between them. That one is silent, not undecidable.
4. **Shell constructs not modeled.** `eval`, `exec` with a computed name,
   aliases and functions, and process substitution (`>(cmd)`). A loop body, a
   brace group, an `if`/`then`/`else` body, a negation and an `xargs`-mediated
   command are no longer here: their leading word is unrecognized, and the
   word-by-word scan described above reaches the command behind it. A `cd`
   inside a subshell or a pipeline stage is not scoped: both the pre-`cd` and
   post-`cd` readings of every later relative target are emitted, so the
   reading that actually ran is always among them — but a `cd` is only honored
   where a segment *starts* with it, never where the scan finds one deeper in,
   since re-anchoring every later target on a guess is worse than missing one.
5. **A link created by some earlier command or by a file-edit tool.** Only an
   `ln` inside *this* command string is visible here. A hard link made a minute
   ago turns an innocuous path into a write of whatever it aliases, and no
   inspection of a later command can see it.

Deliberately over-approximates wherever the two readings cannot be told apart:
a token containing `>` and no whitespace is read as a redirect (the shell reads
`echo x>f` that way, and quoting is already gone by then), a dangling `>` is a
doubt rather than a silence (the shell refuses to run one, so a real command
pays nothing, and it is what a lifted substitution leaves), a `sed` script
operand may be reported as a file, and an option value may be reported as a
`mv`/`ln` source. Naming a path nothing writes costs a caller a refusal it
could have skipped; missing one is the defect this module exists to prevent.

Over-block, re-measured on 547 real command lines from this repository's
Makefile, scripts and documented shell fences: **zero** reach a protected
class, unchanged. 33 of the 547 report undecidable, up from 25 — every one of
the eight added is documentation placeholder text (`<path>`, `<area>`,
`<branch>`), and one *false* target the older reading invented was dropped.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from agentic_workflows.shell_command_parsing import (
    is_control_token,
    strip_shell_wrappers,
    tokenize,
)

#: A token carrying any of these is not a literal path: the shell would rewrite
#: it before the command ran, and what it becomes is not knowable from here.
EXPANSION_CHARACTERS = frozenset("$`*?[]{}")

#: What may follow `>&` without naming a file — a descriptor number, or `-` to
#: close. Anything else after `>&` is bash's "redirect both streams to a file".
FILE_DESCRIPTOR = re.compile(r"^(\d+|-)$")


class DoubtKind(StrEnum):
    """What a doubt is *about*. A caller's policy differs between the two, so
    reporting only prose would force it to parse this back out of a sentence.

    The split is not cosmetic: one says a write is definitely happening and its
    path cannot be read, the other says it is not established that this is a
    write at all — the `>` may be data the command never executes.
    """

    #: A recognized shape writes something; which file it writes cannot be
    #: read from the command. A variable, a command substitution, a glob, a
    #: brace expansion, an operand the shell removed, a relative operand after
    #: an unmodeled `cd`, or a command that will not tokenize.
    UNREADABLE_TARGET = "unreadable target"

    #: Whether this is a write at all is unestablished. Only one shape reaches
    #: it: a `>` inside a quoted word, which is `bash -c '... > f'` as readily
    #: as it is a search pattern or a commit message.
    UNCERTAIN_WRITE = "uncertain write"


class Doubt(NamedTuple):
    """One thing about a command's writes that could not be established."""

    kind: DoubtKind
    reason: str


#: A `>` with nothing after it. The shell refuses to run that as written, so
#: reporting it costs nothing on a command that could actually run — and it is
#: exactly what an unquoted `$(...)` operand leaves behind once the
#: substitution is lifted into its own segment, which is a real write whose
#: path the shell computes.
DANGLING_REDIRECT = Doubt(
    DoubtKind.UNREADABLE_TARGET,
    "output redirect operand: the redirect names nothing — a command "
    "substitution stood here and the shell computes what it becomes, or the "
    "command is malformed, so the path it writes cannot be read from it",
)

#: `-o`, not `--output`: a short option is one dash and one letter, and only a
#: short option glues its value to itself.
SHORT_OPTION_LENGTH = 2

CHDIR_COMMANDS = frozenset({"cd", "pushd", "popd"})
COPY_COMMANDS = frozenset({"cp", "install", "ln", "mv"})
#: Commands whose sources are hazards in their own right, and why: `mv` removes
#: its source, `ln` makes it writable through the name it creates.
SOURCE_IS_A_TARGET = frozenset({"mv", "ln"})

TARGET_DIRECTORY_OPTIONS = frozenset({"-t", "--target-directory"})
#: Options of `cp`/`mv`/`ln`/`install` that consume a separate value token.
#: Getting this set wrong can only mislabel a source, never the destination,
#: which is read as the last operand regardless of what precedes it.
COPY_OPTIONS_WITH_VALUES = frozenset(
    {
        "-t",
        "--target-directory",
        "-S",
        "--suffix",
        "-m",
        "--mode",
        "-o",
        "--owner",
        "-g",
        "--group",
    }
)
INSTALL_DIRECTORY_OPTIONS = frozenset({"-d", "--directory"})

#: `sed` options naming a script, so the first operand is a file rather than the
#: script itself. Their values are skipped when collecting operands.
SED_SCRIPT_OPTIONS = frozenset({"-e", "--expression", "-f", "--file"})
SED_SCRIPT_PREFIXES = ("--expression=", "--file=")
SED_IN_PLACE_LONG = "--in-place"

#: Commands whose every operand is a path they write, create, remove or change
#: the mode of, with the options that consume a separate value token. The sets
#: are per command because `rm -r` takes no value while `truncate -s` does, and
#: one shared set would swallow `rm -r`'s operand.
OPERAND_COMMANDS_WITH_VALUE_OPTIONS = {
    "rm": frozenset(),
    "unlink": frozenset(),
    "truncate": frozenset({"-s", "--size", "-r", "--reference"}),
    "touch": frozenset({"-d", "--date", "-r", "--reference", "-t"}),
    "chmod": frozenset({"--reference"}),
    "chown": frozenset({"--reference"}),
    "mkdir": frozenset({"-m", "--mode"}),
}

#: Fetchers whose output path is named by an option rather than by position.
#: `curl -O` and `wget -O` differ only in case, and only the second names a
#: file, so these are matched exactly as spelled.
OUTPUT_OPTION_COMMANDS = {
    "curl": frozenset({"-o", "--output", "--output-dir"}),
    "wget": frozenset(
        {"-O", "--output-document", "-o", "--output-file", "-P", "--directory-prefix"}
    ),
}


class WriteTarget(NamedTuple):
    """One path a recognized shape writes, and the shape that named it — a
    denial quoting this says which operand of which command it objected to."""

    path: Path
    shape: str


class ShellWriteTargets(NamedTuple):
    """Everything a command was found to write, plus everything about its
    writes that could not be established. `undecidable` is never empty for a
    recognized shape whose operand the shell would rewrite at runtime, so a
    caller that fails closed on it is not silently trusting a guess."""

    targets: tuple[WriteTarget, ...]
    undecidable: tuple[Doubt, ...]


def _quoted_redirect_doubt(token: str) -> Doubt:
    return Doubt(
        DoubtKind.UNCERTAIN_WRITE,
        f"a quoted word carrying a redirect ({token!r}): the shell splits words "
        "on whitespace, so this `>` was quoted — an interpreter script, a search "
        "pattern or a message, and nothing here tells them apart",
    )


def _is_literal_path(token: str) -> bool:
    return not any(character in EXPANSION_CHARACTERS for character in token)


def _option_values(args: list[str], options: frozenset[str]) -> list[tuple[str, str]]:
    """Every value given to one of `options`, in all three spellings a shell
    accepts: separate (`-o V`), long-glued (`--output=V`), and short-glued
    (`-oV`, including inside a bundle like `-soV`).

    A value of `""` means the option was written with nothing after it — the
    operand was there when the command was typed and the shell removed it, so
    the caller reports it rather than reading the silence as no output file.
    Splitting a bundle at the first value-taking letter is getopt's own rule,
    not a spelling this module invented: everything after that letter is the
    value, and an empty remainder takes the next token instead.
    """

    letters = {option[1] for option in options if len(option) == SHORT_OPTION_LENGTH}
    values: list[tuple[str, str]] = []
    index = 0
    while index < len(args):
        argument = args[index]
        index += 1
        if argument == "--":
            break
        if argument.startswith("--"):
            option, separator, value = argument.partition("=")
            if separator and option in options:
                values.append((option, value))
            elif argument in options:
                values.append((argument, args[index] if index < len(args) else ""))
                index += 1
            continue
        if not argument.startswith("-"):
            continue
        position = next(
            (
                place
                for place, letter in enumerate(argument[1:], 1)
                if letter in letters
            ),
            None,
        )
        if position is None:
            continue
        option = f"-{argument[position]}"
        glued = argument[position + 1 :]
        if glued:
            values.append((option, glued))
            continue
        values.append((option, args[index] if index < len(args) else ""))
        index += 1
    return values


def _operands(args: list[str], options_with_values: frozenset[str]) -> list[str]:
    """Non-option tokens, with `--` ending option parsing. A bare `-` is an
    operand: tools spell stdin/stdout that way and it names no path."""

    operands: list[str] = []
    index = 0
    while index < len(args):
        argument = args[index]
        if argument == "--":
            return operands + args[index + 1 :]
        if argument.startswith("-") and argument != "-":
            index += 2 if argument in options_with_values else 1
            continue
        operands.append(argument)
        index += 1
    return operands


def _target_directory(args: list[str]) -> str | None:
    """The `-t`/`--target-directory` value, which makes every operand a source
    and the named directory the destination."""

    for _, value in _option_values(args, TARGET_DIRECTORY_OPTIONS):
        return value
    return None


def _short_option_letters(args: list[str]) -> str:
    """Every bundled short-option letter in `args` — `-Ei` and `-i.bak` both
    carry `i`, and either spelling makes `sed` edit in place."""

    return "".join(
        token[1:]
        for token in args
        if token.startswith("-") and not token.startswith("--")
    )


def _sed_edits_in_place(args: list[str]) -> bool:
    return "i" in _short_option_letters(args) or any(
        token == SED_IN_PLACE_LONG or token.startswith(SED_IN_PLACE_LONG + "=")
        for token in args
    )


def _sed_has_explicit_script(args: list[str]) -> bool:
    """True when a script was given by option, which makes every operand a
    file. Otherwise the first operand is the script."""

    letters = _short_option_letters(args)
    return (
        "e" in letters
        or "f" in letters
        or any(token.startswith(SED_SCRIPT_PREFIXES) for token in args)
    )


class _Walk:
    """One pass over a command's tokens, accumulating what it writes.

    `prefixes` is every directory a later relative operand might be resolved
    against: it starts as "wherever the caller runs this" and gains one entry
    per `cd`, keeping the earlier ones because a `cd` in a subshell does not
    outlive it. Emitting each reading is what makes `cd .git && printf x >
    config` visible as a write to `.git/config`.
    """

    def __init__(self) -> None:
        self.targets: list[WriteTarget] = []
        self.undecidable: list[Doubt] = []
        self.prefixes: list[Path] = [Path()]
        self.base_unknown = False
        self.certain = True

    def unreadable(self, doubt: Doubt) -> None:
        """Note that something about this command's writes could not be
        established, unless the reading that raised it is itself a guess — see
        `flush` for why a scanned-past command reports targets but no doubt."""

        if self.certain:
            self.undecidable.append(doubt)

    def unreadable_target(self, reason: str) -> None:
        """The common case: a recognized shape writes, and the path it writes
        cannot be read from the command."""

        self.unreadable(Doubt(DoubtKind.UNREADABLE_TARGET, reason))

    def record(self, token: str, shape: str) -> None:
        """Note one operand as a write target under every candidate prefix, or
        as undecidable when the shell would rewrite it or when a preceding
        `cd` left no directory to read it against."""

        if not token:
            self.unreadable_target(
                f"{shape}: the operand is empty or absent — the shell removed "
                "what stood here (a command substitution it computes at "
                "runtime, or an expansion that matched nothing), so the path "
                "it names cannot be read from the command"
            )
            return
        if not _is_literal_path(token):
            self.unreadable_target(
                f"{shape}: {token!r} is rewritten by the shell before the command "
                "runs, so the path it names cannot be read from the command"
            )
            return
        candidate = Path(token)
        for prefix in self.prefixes:
            target = WriteTarget(prefix / candidate, shape)
            if target not in self.targets:
                self.targets.append(target)
        if self.base_unknown and not candidate.is_absolute():
            self.unreadable_target(
                f"{shape}: {token!r} is relative and an earlier `cd` in this "
                "command left no directory to resolve it against"
            )

    def record_each(self, tokens: list[str], shape: str) -> None:
        for token in tokens:
            self.record(token, shape)

    def chdir(self, name: str, args: list[str]) -> None:
        operands = _operands(args, frozenset())
        if name != "cd" or len(operands) != 1 or operands[0] == "-":
            self.base_unknown = True
            return
        if not _is_literal_path(operands[0]):
            self.base_unknown = True
            return
        self.prefixes.append(self.prefixes[-1] / operands[0])

    def copy(self, name: str, args: list[str]) -> None:
        operands = _operands(args, COPY_OPTIONS_WITH_VALUES)
        directory = _target_directory(args)
        if directory is not None:
            self.record(directory, f"{name} -t destination directory")
            sources = operands
        elif name == "install" and any(
            token in INSTALL_DIRECTORY_OPTIONS for token in args
        ):
            self.record_each(operands, "install -d created directory")
            return
        elif len(operands) > 1:
            self.record(operands[-1], f"{name} destination operand")
            sources = operands[:-1]
        else:
            if name != "ln":
                # `ln A` is the valid one-operand form, linking A into the
                # working directory. Every other command here needs two, so one
                # operand means the shell removed what stood in the other.
                self.record("", f"{name} destination operand")
            sources = operands
        if name in SOURCE_IS_A_TARGET:
            self.record_each(sources, f"{name} source operand")

    def sed(self, args: list[str]) -> None:
        if not _sed_edits_in_place(args):
            return
        operands = [token for token in _operands(args, SED_SCRIPT_OPTIONS) if token]
        if not _sed_has_explicit_script(args):
            operands = operands[1:]
        self.record_each(operands, "sed -i file operand")

    def dd(self, args: list[str]) -> None:
        for token in args:
            if token.startswith("of="):
                self.record(token.removeprefix("of="), "dd of= operand")

    def output_option(
        self, name: str, args: list[str], options: frozenset[str]
    ) -> None:
        """The value of a named output option, in every spelling: `-o VALUE`,
        `--output=VALUE`, and glued `-oVALUE` — which is the standard way to
        write it, and the one that made both fetchers silent."""

        for option, value in _option_values(args, options):
            self.record(value, f"{name} {option} output operand")

    def flush(self, words: list[str]) -> None:
        """Dispatch one command segment, reading past a leading word it does
        not know.

        `strip_shell_wrappers` removes leading assignments and
        `env`/`sudo`/`nohup`, and only the basename is matched so `/bin/cp` is
        the same command as `cp`. That covers the wrappers a shell has names
        for; it does not cover an *ordinary* command in front of a recognized
        one. `timeout 5 cp ...`, `nice cp ...`, `exec cp ...`, a brace group,
        an `if` body and a loop body all put a recognized command somewhere
        other than first, and reading position zero alone made every one of
        them silent even though the writing command was in the table.

        So the segment is scanned word by word for a name the table knows. The
        deeper reading is a **guess** — `pip install a b` genuinely looks like
        GNU `install` — so it contributes targets, which a caller weighs
        against a protected class, and never doubt, which a caller refuses
        outright. Refusing every `find . -exec chmod 644 {} +` for a brace it
        could not read is the trade that makes a recognizer unusable.
        """

        command = strip_shell_wrappers(words)
        if self.dispatch(command, certain=True):
            return
        for position in range(1, len(command)):
            if self.dispatch(command[position:], certain=False):
                break
        self.certain = True

    def dispatch(self, command: list[str], certain: bool) -> bool:
        """Read `command` as one of the recognized shapes, reporting whether
        its head word named one at all."""

        if not command:
            return False
        name = PurePosixPath(command[0]).name
        args = command[1:]
        self.certain = certain
        if name in CHDIR_COMMANDS:
            # Only a `cd` a segment actually starts with moves the prefix. One
            # guessed at from inside an unrecognized command would re-anchor
            # every later target in the whole command string on that guess.
            if not certain:
                return False
            self.chdir(name, args)
        elif name in COPY_COMMANDS:
            self.copy(name, args)
        elif name == "sed":
            self.sed(args)
        elif name == "tee":
            self.record_each(_operands(args, frozenset()), "tee file operand")
        elif name == "dd":
            self.dd(args)
        elif name in OPERAND_COMMANDS_WITH_VALUE_OPTIONS:
            operands = _operands(args, OPERAND_COMMANDS_WITH_VALUE_OPTIONS[name])
            self.record_each(operands, f"{name} operand")
        elif name in OUTPUT_OPTION_COMMANDS:
            self.output_option(name, args, OUTPUT_OPTION_COMMANDS[name])
        else:
            return False
        return True


class _Redirect(NamedTuple):
    """What a redirect operator opens, and where reading continues.

    At most one of `target` and `unreadable` carries anything. Neither does
    for a descriptor duplication (`2>&1`, `>&-`), which opens no file and is
    not a doubt either.
    """

    target: str | None
    unreadable: Doubt | None
    next_index: int


def _redirect_operand(tokens: list[str], index: int) -> _Redirect | None:
    """The file a redirect at `tokens[index]` writes, or why none could be
    read, or None when this token opens no redirect at all.

    The operand may be glued to the operator (`x>f`) because `>` is not one of
    the tokenizer's punctuation characters, and `>|` and `>&` split further
    because `|` and `&` are.

    Whitespace inside the token is the discriminator for the one case this
    cannot decide: tokens are already split on whitespace, so a space next to
    the `>` proves the operator came from inside a quoted word. That word is
    `bash -c \'... > <path>\'` as often as it is `rg -n \'x > <path>\'` or a
    commit message, and nothing here tells a script from a pattern — so it is
    reported as a doubt rather than claimed as a write.
    """

    token = tokens[index]
    position = token.find(">")
    if position < 0:
        return None
    if any(character.isspace() for character in token):
        return _Redirect(None, _quoted_redirect_doubt(token), index + 1)
    glued = token[position + 1 :].removeprefix(">").removeprefix("|")
    if glued:
        return _Redirect(glued, None, index + 1)

    following = tokens[index + 1] if index + 1 < len(tokens) else None
    if following is None:
        return _Redirect(None, DANGLING_REDIRECT, index + 1)
    if following in {"&", "|"}:
        after = tokens[index + 2] if index + 2 < len(tokens) else None
        if after is None or is_control_token(after):
            return _Redirect(None, DANGLING_REDIRECT, index + 2)
        if following == "&" and FILE_DESCRIPTOR.match(after):
            return _Redirect(None, None, index + 3)
        return _Redirect(after, None, index + 3)
    if is_control_token(following):
        return _Redirect(None, DANGLING_REDIRECT, index + 1)
    return _Redirect(following, None, index + 2)


def write_targets(command: str) -> ShellWriteTargets:
    """Every file path `command` is found to write, plus every write of it that
    could not be established. See this module's docstring for the exact table
    of recognized shapes and the enumerated shapes outside it."""

    try:
        tokens = tokenize(command)
    except ValueError as error:
        return ShellWriteTargets(
            (),
            (
                Doubt(
                    DoubtKind.UNREADABLE_TARGET,
                    f"the command could not be tokenized ({error}), so nothing "
                    "about what it writes could be established",
                ),
            ),
        )

    walk = _Walk()
    words: list[str] = []
    index = 0
    while index < len(tokens):
        redirect = _redirect_operand(tokens, index)
        if redirect is not None:
            index = redirect.next_index
            if redirect.target is not None:
                walk.record(redirect.target, "output redirect operand")
            elif redirect.unreadable is not None:
                walk.unreadable(redirect.unreadable)
            continue
        if is_control_token(tokens[index]):
            walk.flush(words)
            words = []
        else:
            words.append(tokens[index])
        index += 1
    walk.flush(words)

    return ShellWriteTargets(tuple(walk.targets), tuple(walk.undecidable))
