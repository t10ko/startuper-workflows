from __future__ import annotations

import io
import tokenize

MASKED_TOKEN_TYPES = {tokenize.STRING, tokenize.COMMENT}


def _blank_token_span(
    mutable_lines: list[list[str]],
    start: tuple[int, int],
    end: tuple[int, int],
) -> None:
    start_row, start_col = start
    end_row, end_col = end
    for row_idx in range(start_row - 1, end_row):
        if row_idx >= len(mutable_lines):
            return
        line = mutable_lines[row_idx]
        col_start = start_col if row_idx == start_row - 1 else 0
        col_end = end_col if row_idx == end_row - 1 else len(line)
        for col_idx in range(col_start, min(col_end, len(line))):
            if line[col_idx] not in "\r\n":
                line[col_idx] = " "


def code_only_content(content: str) -> str:
    mutable_lines = [list(line) for line in content.splitlines(keepends=True)]
    try:
        tokens = tokenize.generate_tokens(io.StringIO(content).readline)
        for token in tokens:
            if token.type in MASKED_TOKEN_TYPES:
                _blank_token_span(mutable_lines, token.start, token.end)
    except tokenize.TokenError:
        return content
    return "".join("".join(line) for line in mutable_lines)
