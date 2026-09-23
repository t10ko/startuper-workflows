from __future__ import annotations

import ast
import re
from pathlib import Path

from agentic_workflows.python_antipattern_scanner.models import RuleFinding
from agentic_workflows.python_antipattern_scanner.rules import (
    ALLOW_COMMENT,
    LINE_RULES,
    PATH_STR_PATTERN,
    RULE_4_5,
    RULE_10,
    RULE_PROJECT_PATH_RELATIVITY,
)

from .support import BOUNDARY_COMMENT, relative_path, skip_line_rule

CAST_CALL_PATTERN = re.compile(r"(?<![a-zA-Z0-9_])cast\s*\(")
PROJECT_PATH_JOIN_MARKERS = ("project_folder /", "project_path(")


def scan_line_rules(
    path: Path,
    lines: list[str],
    code_lines: list[str],
    project_root: Path | None,
) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    for lineno, line in enumerate(lines, 1):
        code_line = code_lines[lineno - 1] if lineno <= len(code_lines) else line
        for line_rule in LINE_RULES:
            rule_id = line_rule.definition.rule_id
            if rule_id == "RULE_10" or skip_line_rule(line, rule_id):
                continue

            if rule_id == "RULE_15":
                scan_line = line
            elif rule_id == "RULE_2":
                scan_line = line if CAST_CALL_PATTERN.search(code_line) else ""
            elif rule_id == "RULE_17":
                scan_line = code_line if line[:1].isspace() else ""
            else:
                scan_line = code_line

            if line_rule.pattern.search(scan_line):
                findings.append(
                    RuleFinding(
                        path=relative_path(path, project_root),
                        line=lineno,
                        rule_id=line_rule.definition.rule_id,
                        message=line_rule.definition.message,
                        evidence=line.strip(),
                        why=line_rule.definition.why,
                        best_fix=line_rule.definition.best_fix,
                        group_title=line_rule.definition.group_title,
                    )
                )
    return findings


def scan_rule_10(
    path: Path,
    lines: list[str],
    code_only: str,
    project_root: Path | None,
) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    max_evidence_lines = 3
    rule_10_line_rule = next(
        (r for r in LINE_RULES if r.definition.rule_id == "RULE_10"), None
    )
    if rule_10_line_rule is None:
        return findings

    for match in re.finditer(rule_10_line_rule.pattern, code_only):
        start_index = match.start()
        lineno = code_only[:start_index].count("\n") + 1
        matched_line_count = match.group(0).count("\n") + 1
        evidence_lines = lines[lineno - 1 : lineno - 1 + matched_line_count]
        if any(ALLOW_COMMENT in line for line in evidence_lines):
            continue

        evidence = " ".join(
            line.strip() for line in evidence_lines[:max_evidence_lines]
        )
        if len(evidence_lines) > max_evidence_lines:
            evidence += " ..."

        findings.append(
            RuleFinding(
                path=relative_path(path, project_root),
                line=lineno,
                rule_id=RULE_10.rule_id,
                message=RULE_10.message,
                evidence=evidence,
                why=RULE_10.why,
                best_fix=RULE_10.best_fix,
                group_title=RULE_10.group_title,
            )
        )
    return findings


def scan_path_str_rule(
    path: Path,
    lines: list[str],
    code_lines: list[str],
    project_root: Path | None,
) -> list[RuleFinding]:
    findings: list[RuleFinding] = []
    for lineno, line in enumerate(lines, 1):
        if ALLOW_COMMENT in line:
            continue
        code_line = code_lines[lineno - 1] if lineno <= len(code_lines) else line
        if PATH_STR_PATTERN.search(code_line):
            findings.append(
                RuleFinding(
                    path=relative_path(path, project_root),
                    line=lineno,
                    rule_id=RULE_4_5.rule_id,
                    message=RULE_4_5.message,
                    evidence=line.strip(),
                    why=RULE_4_5.why,
                    best_fix=RULE_4_5.best_fix,
                    group_title=RULE_4_5.group_title,
                )
            )
    return findings


def scan_project_path_relativity_rule(
    path: Path,
    lines: list[str],
    content: str,
    project_root: Path | None,
) -> list[RuleFinding]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    findings: list[RuleFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.IfExp):
            continue
        if not _is_project_path_hybrid_ifexp(node, content):
            continue

        lineno = node.test.lineno
        evidence = lines[lineno - 1].strip() if 1 <= lineno <= len(lines) else ""
        if ALLOW_COMMENT in evidence or BOUNDARY_COMMENT in evidence:
            continue
        findings.append(
            RuleFinding(
                path=relative_path(path, project_root),
                line=lineno,
                rule_id=RULE_PROJECT_PATH_RELATIVITY.rule_id,
                message=RULE_PROJECT_PATH_RELATIVITY.message,
                evidence=evidence,
                why=RULE_PROJECT_PATH_RELATIVITY.why,
                best_fix=RULE_PROJECT_PATH_RELATIVITY.best_fix,
                group_title=RULE_PROJECT_PATH_RELATIVITY.group_title,
            )
        )
    return findings


def _is_project_path_hybrid_ifexp(node: ast.IfExp, content: str) -> bool:
    """A branch on ``<path>.is_absolute()`` that then joins a project path.

    **What this does not reach.** ``is_absolute`` is matched in attribute
    form only, which is the only form it admits: it is a ``pathlib.Path``
    method, so no import binds it as a bare name.
    """
    if not isinstance(node.test, ast.Call):
        return False
    if not isinstance(node.test.func, ast.Attribute):
        return False
    if node.test.func.attr != "is_absolute":
        return False

    segment = ast.get_source_segment(content, node)
    if segment is None:
        return False
    return any(marker in segment for marker in PROJECT_PATH_JOIN_MARKERS)
