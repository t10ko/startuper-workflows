from __future__ import annotations

import ast
import re
from pathlib import Path

from .models import OptionalArgFinding, OptionalArgScanResult, OptionalRepairMatch
from .rules import (
    ALLOW_COMMENT,
    BOUNDARY_ERROR_TEXT,
    CALLABLE_MARKERS,
    OPTIONAL_EMPTY_PATTERNS,
)


def scan_optional_arg_shims(path: Path, content: str) -> list[OptionalArgFinding]:
    return scan_optional_arg_shims_with_notes(path, content).findings


def scan_optional_arg_shims_with_notes(
    path: Path,
    content: str,
) -> OptionalArgScanResult:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return OptionalArgScanResult(findings=[], omitted_notes=[])

    lines = content.splitlines()
    findings: list[OptionalArgFinding] = []
    omitted_notes: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        function_lines = lines[node.lineno - 1 : node.end_lineno]
        for parameter_name, annotation, _optional_line in _iter_optional_parameters(
            node
        ):
            if _is_optional_callback(annotation):
                continue

            repair_match = _find_optional_repair_match(
                parameter_name,
                function_lines,
                base_line=node.lineno,
            )
            if repair_match is None:
                continue

            if _is_boundary_validator(parameter_name, function_lines):
                omitted_notes.append(
                    f"Excluded {path.as_posix()}:{node.name}({parameter_name}) because it validates a boundary contract instead of shimming."
                )
                continue

            findings.append(
                OptionalArgFinding(
                    path=path,
                    line=repair_match.line,
                    function_name=node.name,
                    parameter_name=parameter_name,
                    annotation=annotation,
                    evidence=repair_match.evidence,
                    why="The function repairs missing input immediately, which suggests the parameter should be required upstream.",
                    best_fix="Require the value at the call boundary or normalize it once before calling this function.",
                )
            )
    return OptionalArgScanResult(
        findings=sorted(
            findings,
            key=lambda f: (
                f.path.as_posix(),
                f.line,
                f.function_name,
                f.parameter_name,
            ),
        ),
        omitted_notes=sorted(dict.fromkeys(omitted_notes)),
    )


def _iter_optional_parameters(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[str, str, int]]:
    parameters = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
    defaults = [None] * (len(parameters) - len(node.args.defaults)) + list(
        node.args.defaults
    )
    results: list[tuple[str, str, int]] = []
    for arg, default in zip(parameters, defaults, strict=True):
        if arg.arg in {"self", "cls"}:
            continue
        annotation = ast.unparse(arg.annotation) if arg.annotation is not None else ""
        is_optional = "None" in annotation or _is_none_constant(default)
        if not is_optional:
            continue
        results.append((arg.arg, annotation, arg.lineno))
    return results


def _is_none_constant(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _find_optional_repair_match(
    parameter_name: str,
    function_lines: list[str],
    *,
    base_line: int,
) -> OptionalRepairMatch | None:
    inline_match = _find_inline_optional_repair(
        parameter_name,
        function_lines,
        base_line=base_line,
    )
    if inline_match is not None:
        return inline_match
    return _find_guard_then_assignment(
        parameter_name, function_lines, base_line=base_line
    )


def _find_inline_optional_repair(
    parameter_name: str,
    function_lines: list[str],
    *,
    base_line: int,
) -> OptionalRepairMatch | None:
    parameter_pattern = re.compile(rf"\b{re.escape(parameter_name)}\b")
    for index, line in enumerate(function_lines):
        if ALLOW_COMMENT in line:
            continue
        if not parameter_pattern.search(line):
            continue
        for pattern in OPTIONAL_EMPTY_PATTERNS.values():
            if re.search(pattern.format(name=re.escape(parameter_name)), line):
                return OptionalRepairMatch(
                    line=base_line + index,
                    evidence=line.strip(),
                )
    return None


def _find_guard_then_assignment(
    parameter_name: str,
    function_lines: list[str],
    *,
    base_line: int,
) -> OptionalRepairMatch | None:
    guard_patterns = [
        re.compile(rf"if\s+{re.escape(parameter_name)}\s+is\s+None\s*:"),
        re.compile(rf"if\s+not\s+{re.escape(parameter_name)}\s*:"),
    ]
    assignment_pattern = re.compile(
        rf"{re.escape(parameter_name)}\s*=\s*(\{{\}}|\[\]|\"\"|\(\))"
    )

    for index, line in enumerate(function_lines):
        stripped = line.strip()
        if not any(pattern.fullmatch(stripped) for pattern in guard_patterns):
            continue
        for next_index in range(index + 1, min(index + 4, len(function_lines))):
            next_line = function_lines[next_index].strip()
            if assignment_pattern.search(next_line):
                return OptionalRepairMatch(
                    line=base_line + next_index,
                    evidence=next_line,
                )
    return None


def _is_boundary_validator(parameter_name: str, function_lines: list[str]) -> bool:
    normalized_name = parameter_name.lower()
    for line in function_lines:
        lowered = line.lower()
        if (
            "raise valueerror" not in lowered
            and "raise filenotfounderror" not in lowered
        ):
            continue
        if any(marker in lowered for marker in BOUNDARY_ERROR_TEXT):
            return True
        if normalized_name in lowered:
            return True
    return False


def _is_optional_callback(annotation: str) -> bool:
    return any(marker in annotation for marker in CALLABLE_MARKERS)
