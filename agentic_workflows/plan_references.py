"""Resolve the identifiers a plan's task section cites into their full text.

A task section names what it must satisfy by identifier only -- `REQ-018`,
`DD-001` -- while the sentences those identifiers stand for live in a separate
specification document. An implementer given only the identifiers rebuilds their
meaning by searching the repository, one narrow read at a time, and every one of
those reads stays in its context for the rest of the run.

Nothing here is a second store of a requirement's text: a resolved reference is
read from the owning document on every call and never written back, so the
document stays the only place a requirement is edited
(`.agents/rules/single-source-of-truth.md`).

A definition is an identifier standing in a defining position, and only there:
at the front of a heading title, at the front of a bullet's bold lead-in, or at
the front of a table row's first cell -- where a plan states a criterion it
creates itself, as a row of its scenario ledger and of its test matrix. The
front is read past any emphasis or code marks. A heading title or a first cell
holds a run of identifiers separated by commas (`N-9, N-10` defines both) and a
bullet's lead-in defines only the first identifier it opens with; any other
separator ends the run, so in `S-61 / REQ-037` the second identifier is a
reference. An identifier mentioned anywhere else is a citation.
`resolve_citations` decides which definition wins when several documents define
one.

A fenced block is quoted or example text, so its lines are never document
structure: they define no identifier (as a heading title, a bullet lead-in or a
table first cell), they end no block of a definition that contains the fence, and
they are otherwise ordinary text of whatever block holds them.
`src.utils.markdown_fences` states what counts as a fence: what it reads and what it
leaves unread.

The identifier shape is structural rather than a list of known prefixes: a
citation is a token shaped like `<PREFIX>-<number>` whose prefix some supplied
document actually defines. That keeps a new prefix working without an edit here,
and keeps `UTF-8` from reading as a missing requirement. An identifier glued to
a closing underscore (`_AC-031_`) is not read, because `_` is a word character
and the shape is bounded by a word boundary; letting an underscore bound it would
also make the snake-case name `GET_REQ-12` cite `REQ-12`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from agentic_workflows.markdown_fences import Fence, fence_lines

_IDENTIFIER = re.compile(r"\b([A-Z][A-Z0-9]{0,7})-(\d{1,4}[a-z]?)\b")
_IDENTIFIER_RUN = re.compile(rf"{_IDENTIFIER.pattern}(?:\s*,\s*{_IDENTIFIER.pattern})*")
_MARKS = "*_`"
_HEADING = re.compile(r"^(#+)\s+(.*)$")
_TITLE_DEPTH = 1
_BULLET = re.compile(r"^\s*[-*]\s+\*\*(.*)$")
# A bullet: hyphen, asterisk or plus. The fence leaf's list-marker rule is different and wider.
_BULLET_MARKER = re.compile(r"^\s*[-*+]\s+")
_LINK_TARGET = re.compile(r"[\w./-]+\.md")
_SEPARATOR_CELL = re.compile(r":?-+:?")


@dataclass(frozen=True)
class Reference:
    """One cited identifier, with the document its text was read from."""

    identifier: str
    source: Path
    text: str


def _strip_marks(text: str, *, front_only: bool = False) -> str:
    """*text* without the whitespace, emphasis marks and code marks at its ends.

    Both ends are peeled until neither holds any, so `` `**Spec**` `` and
    `* Spec _` come out as `Spec`; *front_only* leaves the back alone.
    """
    peeled = ""
    while peeled != text:
        peeled = text
        text = text.lstrip().lstrip(_MARKS)
        if not front_only:
            text = text.rstrip().rstrip(_MARKS)
    return text


def _leading_identifiers(text: str) -> list[str]:
    """The identifiers *text* opens with, in order, or `[]` when it opens with none.

    Emphasis and code marks and whitespace in front are formatting, not content,
    so `**S-61**` opens with `S-61`. A run of identifiers separated by commas is
    returned whole (`N-9, N-10` yields both); any other separator ends it, so in
    `S-61 / REQ-037` the second identifier is a reference to another criterion.
    What a caller takes of the run is its own rule: a table row is one record
    keyed by its first cell, so a comma-listed key names that record's subjects,
    while a bullet lead-in takes only its first identifier (`collect_definitions`).

    Anchored at the front on purpose: an identifier mentioned partway through a
    sentence is a citation, and only one in a defining position is a definition.
    """
    run = _IDENTIFIER_RUN.match(_strip_marks(text, front_only=True))
    if run is None:
        return []
    return [
        f"{match.group(1)}-{match.group(2)}"
        for match in _IDENTIFIER.finditer(run.group(0))
    ]


def _header_label(label: str) -> str | None:
    """The name a header line's *label* spells, or `None` when it spells no name.

    *label* is what precedes the line's first colon, read as a person reads it: a
    bullet marker and any emphasis or code marks around the name are formatting, so
    `- **Spec:**`, `` `Spec:` `` and `Spec:` all name `Spec`. A label that is empty
    or holds a space is prose (`See also`), not a name.
    """
    marker = _BULLET_MARKER.match(label)
    name = _strip_marks(label[marker.end() :] if marker else label)
    return name if name and " " not in name else None


def _heading_block(
    lines: list[str], fences: list[Fence], start: int, depth: int
) -> list[str]:
    """Lines from *start* up to the next heading at *depth* or shallower.

    A fenced line never ends the block, whatever it looks like: a heading-like line
    in a quoted example belongs to the block that holds the example.
    """
    block = [lines[start]]
    for line, fence in zip(lines[start + 1 :], fences[start + 1 :], strict=True):
        heading = _HEADING.match(line)
        if heading and len(heading.group(1)) <= depth and fence is Fence.OUTSIDE:
            break
        block.append(line)
    return block


def _indentation(line: str) -> int:
    return len(line) - len(line.lstrip())


def _bullet_block(lines: list[str], fences: list[Fence], start: int) -> list[str]:
    """Lines from *start* up to the line that ends that bullet, by its indentation.

    Let `b` be the number of leading whitespace characters of the bullet's line. A
    following line ends the bullet when it is a heading, or a bullet line
    (`-`, `*` or `+` then whitespace) indented no deeper than `b`, or a non-blank
    line indented no deeper than `b` that comes after a blank line. A non-blank
    line with no blank line before it that is no bullet line continues the
    bullet at any indentation, which is how a wrapped line reads. After a blank
    line only a line indented deeper than `b` continues the bullet (a nested
    bullet, a paragraph, an example), and the blank lines before it belong to the
    block. So a nested bullet stops at its next sibling and at a shallower bullet
    instead of running on into them.

    A fence is judged where it opens: its opening line is one more line under the
    rules above, so a fence indented deeper than `b` belongs to the bullet and one
    indented no deeper than `b` after a blank line ends it. Every later line of the
    fence, its closing line included, is left out of the judgement: it never ends
    the bullet, and a blank line inside it never counts as the blank line those
    rules wait for, so the column-zero lines of a fence inside the bullet stay in
    its block.

    The blank lines that trail the bullet, up to the ending line or the end of the
    document, come back too, for the caller to trim as it does a heading's block.
    Not read: a tab counts as one character.
    """
    depth = _indentation(lines[start])
    after_blank = False
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if fences[index] in (Fence.INSIDE, Fence.CLOSING):
            continue
        if not line.strip():
            after_blank = True
        elif _HEADING.match(line) or (
            _indentation(line) <= depth and (after_blank or _BULLET_MARKER.match(line))
        ):
            return lines[start:index]
    return lines[start:]


def _is_table_row(line: str) -> bool:
    return line.lstrip().startswith("|")


def _is_separator_row(line: str) -> bool:
    """A table row whose every cell is hyphens with optional alignment colons."""
    if not _is_table_row(line):
        return False
    cells = line.strip().strip("|").split("|")
    return all(_SEPARATOR_CELL.fullmatch(cell.strip()) for cell in cells)


def _first_cell_identifiers(line: str) -> list[str]:
    """The identifiers a table row's first cell opens with, or `[]`.

    Only the first cell is read: an identifier in a later cell is a citation.
    """
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    return _leading_identifiers(stripped[1:].split("|", 1)[0])


def _table_header(lines: list[str], row: int) -> int | None:
    """Index of the header row of the table the line at *row* sits in, if any.

    Walks up through the table rows directly above and stops at the first line
    that is not one, so a row cut off from every header by a blank line or prose
    belongs to no table of the shape this reads.
    """
    for index in range(row - 1, -1, -1):
        if not _is_table_row(lines[index]):
            return None
        if _is_separator_row(lines[index + 1]):
            return index
    return None


def collect_definitions(document: str) -> dict[str, str]:
    """Every identifier *document* defines by heading or bullet, with its full text.

    A heading defines every identifier its title opens with
    (`_leading_identifiers`) and a bullet only the first its bold lead-in opens
    with; a plain bullet defines nothing. A lead-in listing several identifiers is
    a statement about the group, so handing its one block to each would give an
    identifier a block that describes another's; a later one stays a citation.
    The first definition of an identifier wins, so a later traceability table
    restating it cannot overwrite the real one.

    A fenced line is never examined as a heading or as a bullet, so a definition
    quoted in a fence defines nothing and a heading quoted in one ends no block.
    """
    lines = document.splitlines()
    fences = fence_lines(lines)
    definitions: dict[str, str] = {}
    for index, line in enumerate(lines):
        if fences[index] is not Fence.OUTSIDE:
            continue
        heading = _HEADING.match(line)
        if heading:
            for identifier in _leading_identifiers(heading.group(2)):
                if identifier not in definitions:
                    block = _heading_block(lines, fences, index, len(heading.group(1)))
                    definitions[identifier] = "\n".join(block).rstrip()
            continue
        bullet = _BULLET.match(line)
        if bullet:
            for identifier in _leading_identifiers(bullet.group(1))[:1]:
                if identifier not in definitions:
                    definitions[identifier] = "\n".join(
                        _bullet_block(lines, fences, index)
                    ).rstrip()
    return definitions


def collect_row_definitions(document: str) -> dict[str, str]:
    """Every identifier *document* defines by a table row, mapped to those rows.

    A row read alone is a list of unlabelled cells, so an identifier's text is,
    for each table holding a row whose first cell opens with it
    (`_first_cell_identifiers`), the table's header row, its separator row and
    every such row in document order; an identifier with rows in several tables
    gets one block per table, a blank line apart. A row with no header above it
    defines nothing.

    A row on a fenced line defines nothing, and no header is found across a fence:
    its opening and closing lines are no table row, so the walk up from a row stops
    at them (`_table_header`).

    This does not consult `collect_definitions`, so an identifier a heading or
    bullet also defines appears here too; `resolve_citations` decides between them.
    """
    lines = document.splitlines()
    fences = fence_lines(lines)
    rows_by_table: dict[str, dict[int, list[str]]] = {}
    for index, line in enumerate(lines):
        if fences[index] is not Fence.OUTSIDE:
            continue
        identifiers = _first_cell_identifiers(line)
        if not identifiers:
            continue
        header = _table_header(lines, index)
        if header is not None:
            for identifier in identifiers:
                tables = rows_by_table.setdefault(identifier, {})
                tables.setdefault(header, []).append(line)
    return {
        identifier: "\n\n".join(
            "\n".join([lines[header], lines[header + 1], *rows]).rstrip()
            for header, rows in tables.items()
        )
        for identifier, tables in rows_by_table.items()
    }


def resolve_citations(
    task_text: str, documents: dict[Path, str]
) -> tuple[list[Reference], list[str]]:
    """Every identifier *task_text* cites, split into resolved and unresolved.

    *documents* is searched in insertion order, so a plan listed before its spec
    wins where both define one identifier by heading or bullet -- the narrower,
    task-local statement is the one an implementer needs. A table row is read
    only for an identifier no document defines by heading or bullet, whatever
    the order: a plan's ledger restates a spec criterion in one terse line, and
    that line must not shadow the criterion's full text. An identifier whose
    prefix no document defines at all is not a citation and appears in neither
    list.
    """
    known: dict[str, tuple[Path, str]] = {}
    row_known: dict[str, tuple[Path, str]] = {}
    for path, document in documents.items():
        for identifier, text in collect_definitions(document).items():
            known.setdefault(identifier, (path, text))
        for identifier, text in collect_row_definitions(document).items():
            row_known.setdefault(identifier, (path, text))
    prefixes = {identifier.split("-", 1)[0] for identifier in (*known, *row_known)}

    resolved: list[Reference] = []
    unresolved: list[str] = []
    seen: set[str] = set()
    for match in _IDENTIFIER.finditer(task_text):
        identifier = f"{match.group(1)}-{match.group(2)}"
        if identifier in seen or match.group(1) not in prefixes:
            continue
        seen.add(identifier)
        found = known.get(identifier) or row_known.get(identifier)
        if found is None:
            unresolved.append(identifier)
        else:
            resolved.append(
                Reference(identifier=identifier, source=found[0], text=found[1])
            )

    resolved.sort(key=lambda reference: reference.identifier)
    unresolved.sort()
    return resolved, unresolved


def linked_document_paths(plan_text: str) -> dict[str, Path]:
    """The documents a plan's header links, keyed by header label.

    Reads the labels the plan itself carries rather than a fixed list, so a plan
    linking a further document is picked up without an edit here, and a link
    written as a bullet is read like a plain line (`_header_label`). The header
    block is every line before the first heading of level two or deeper; a
    level-one heading is the plan's title, so it neither ends the block nor is
    read for links. Nothing after the block is considered, so a path mentioned in
    the body is never mistaken for a link.

    A fenced line is neither a link line nor a heading that ends the block, so a
    label quoted in a fence yields no link and a level-two heading quoted in one
    leaves the header running.
    """
    lines = plan_text.splitlines()
    links: dict[str, Path] = {}
    for line, fence in zip(lines, fence_lines(lines), strict=True):
        if fence is not Fence.OUTSIDE:
            continue
        heading = _HEADING.match(line)
        if heading:
            if len(heading.group(1)) > _TITLE_DEPTH:
                break
            continue
        label, separator, remainder = line.partition(":")
        if not separator:
            continue
        name = _header_label(label)
        if name is None:
            continue
        target = _LINK_TARGET.search(remainder)
        if target:
            links[name] = Path(target.group(0))
    return links
