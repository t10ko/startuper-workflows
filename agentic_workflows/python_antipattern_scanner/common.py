from __future__ import annotations

from pathlib import Path

from agentic_workflows.types import JSONDict, JSONValue


def as_json_dict(data: JSONValue) -> JSONDict | None:
    if isinstance(data, dict):
        return data
    return None


def tool_input_dict(payload: JSONDict) -> JSONDict | None:
    raw_input = payload.get("tool_input")
    return as_json_dict(raw_input)


def extract_tool_input_contents(tool_input: JSONDict) -> list[str]:
    contents: list[str] = []
    for key in ("CodeContent", "ReplacementContent", "content", "new_string"):
        value = tool_input.get(key)
        if isinstance(value, str):
            contents.append(value)

    raw_chunks = tool_input.get("ReplacementChunks")
    if not isinstance(raw_chunks, list):
        return contents

    for chunk in raw_chunks:
        chunk_dict = as_json_dict(chunk)
        if chunk_dict is None:
            continue
        replacement = chunk_dict.get("ReplacementContent")
        if isinstance(replacement, str):
            contents.append(replacement)
    return contents


def hook_target_relative_path(payload: JSONDict, project_root: Path) -> Path | None:
    tool_input = tool_input_dict(payload)
    if tool_input is None:
        return None
    target_file = tool_input.get("TargetFile")
    if not isinstance(target_file, str) or not target_file.strip():
        return None

    target_path = Path(target_file)
    if target_path.is_absolute():
        try:
            return target_path.relative_to(project_root)
        except ValueError:
            return target_path
    return target_path


def is_src_path(path: Path) -> bool:
    posix = path.as_posix()
    return posix.startswith(("src/", "scripts/"))


def line_at(lines: list[str], lineno: int) -> str:
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1]
    return ""
