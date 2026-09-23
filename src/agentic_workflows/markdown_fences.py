"""Where each line of a Markdown document sits among its fenced blocks.

A fence opens on a line that, after any leading spaces or tabs and any list markers,
starts with three or more backticks or three or more tildes. A list marker is `-`,
`+` or `*`, or one to nine digits and then `.` or `)`, and each is followed by one to
four spaces or one tab, so the line of a list item (nested or not) that opens a fence
opens it. A backtick fence's info string (the rest of the line) must hold no backtick,
so a line that opens with inline code stays text. It closes on the next line that,
after any leading spaces or tabs, is a run of the same character at least as long as
the opening run and nothing else but trailing spaces or tabs, so a shorter run, the
other character, text after the run or a list marker before it leaves it open, and a
fence that never closes runs to the end of the document, as CommonMark reads it.

Not read: an indented code block as a block of its own (four spaces cannot be told
from a list continuation, so a run after any number of leading spaces still opens a
fence and the block's other lines stay text), a list marker followed by five or more
spaces before the run (CommonMark's indented code block inside the item), a list
marker followed by mixed spacing before the run (the spacing is read as one to four
spaces or one tab, so a space then a tab, a tab then a space or two spaces then a tab
opens nothing, where CommonMark counts the spacing in columns to the next tab stop
and reads a fence there when it comes to four columns or fewer, and the leaf then
reads that fence's indented closing line as an opener), a fence inside a blockquote
(`>` before the run, with or without a list marker beside it), a fence marker that
follows other text on its line (inline code, text after a list marker), and a
container's own extent: a fence a list item opens closes on any later line that is
only a closing run, whatever its indentation, where CommonMark also ends it with the
list item. A list marker is read wherever its line stands, so a number other than 1
right after a paragraph line, which CommonMark takes for paragraph text, opens a
fence here.

A leaf: it imports only the standard library, so a module of any layer may read it.
"""

from __future__ import annotations

import re
from enum import Enum, auto

_LIST_MARKER = r"(?:[-+*]|[0-9]{1,9}[.)])(?:[ ]{1,4}|\t)"
_FENCE_RUN = re.compile(r"[ \t]*(?:" + _LIST_MARKER + r")*(`{3,}|~{3,})")


class Fence(Enum):
    """Where a line sits among the fenced blocks of its document.

    `OUTSIDE` is a line that is part of no fenced block, `OPENING` the line that
    opens one, `INSIDE` each line between the opening and the closing line and
    `CLOSING` the line that closes it.
    """

    OUTSIDE = auto()
    OPENING = auto()
    INSIDE = auto()
    CLOSING = auto()


def _opening_run(line: str) -> str:
    """The run of backticks or tildes *line* opens a fence with, or `""` if it opens none."""
    opening = _FENCE_RUN.match(line)
    if opening is None:
        return ""
    run = opening.group(1)
    if run[0] == "`" and "`" in line[opening.end() :]:
        return ""
    return run


def _closes_fence(line: str, run: str) -> bool:
    """Whether *line* is nothing but a run of *run*'s character at least as long as *run*."""
    closing = line.strip(" \t")
    return len(closing) >= len(run) and closing == run[0] * len(closing)


def fence_lines(lines: list[str]) -> list[Fence]:
    """One entry per line of *lines*: where that line sits among the fenced blocks.

    A fence opens on a line that, after any leading spaces or tabs and any list
    markers, starts with three or more backticks or three or more tildes. A list
    marker is `-`, `+` or `*`, or one to nine digits and then `.` or `)`, and each is
    followed by one to four spaces or one tab, so the line of a list item (nested or
    not) that opens a fence opens it; five or more spaces after a marker make an
    indented code block, and such a line opens nothing. A backtick fence's info
    string (the rest of the line) must hold no backtick, so a line that opens with
    inline code stays text; a tilde fence's is free. It closes on the next line that,
    after any leading spaces or tabs, is a run of the same character at least as long
    as the opening run and nothing else but trailing spaces or tabs, so a shorter
    run, the other character, text after the run or a list marker before it leaves
    it open. A fence that never closes runs to the end of the document, as CommonMark
    reads it.

    The opening line is `OPENING`, every line between it and the closing line is
    `INSIDE` and the closing line is `CLOSING`; for a fence that never closes, every
    line after its opening line is `INSIDE`. The delimiters are told apart from the
    body because a reader may judge them differently. A closing line never opens the
    next fence, but the line after it may, so two fences that touch are told apart:
    the second one's first line is `OPENING`.

    Computed once per document and handed to the readers that need it. *lines* is
    left untouched.

    Not read: an indented code block as a block of its own (four spaces cannot be
    told from a list continuation, so a run after any number of leading spaces still
    opens a fence and the block's other lines stay text), a list marker followed by
    five or more spaces before the run (CommonMark's indented code block inside the
    item), a list marker followed by mixed spacing before the run (the spacing is
    read as one to four spaces or one tab, so a space then a tab, a tab then a space
    or two spaces then a tab opens nothing, where CommonMark counts the spacing in
    columns to the next tab stop and reads a fence there when it comes to four
    columns or fewer, and the leaf then reads that fence's indented closing line as
    an opener), a fence inside a blockquote (`>` before the run, with or without a
    list marker beside it), a fence marker that follows other text on its line
    (inline code, text after a list marker), and a container's own extent: a fence a
    list item opens closes on any later line that is only a closing run, whatever
    its indentation, where CommonMark also ends it with the list item. A list
    marker is read wherever its line stands, so a number other than 1 right after a
    paragraph line, which CommonMark takes for paragraph text, opens a fence here.
    """
    fences: list[Fence] = []
    run = ""
    for line in lines:
        if run:
            if _closes_fence(line, run):
                fences.append(Fence.CLOSING)
                run = ""
            else:
                fences.append(Fence.INSIDE)
            continue
        run = _opening_run(line)
        fences.append(Fence.OPENING if run else Fence.OUTSIDE)
    return fences
