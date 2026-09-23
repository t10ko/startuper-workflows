from __future__ import annotations

from pathlib import Path

from agentic_workflows.python_antipattern_scanner.common import (
    extract_tool_input_contents,
    hook_target_relative_path,
    is_src_path,
    tool_input_dict,
)
from agentic_workflows.python_antipattern_scanner.models import AntipatternReport, RuleFinding
from agentic_workflows.types import JSONDict

from .ast_rules import scan_ast_rules
from .line_rules import (
    scan_line_rules,
    scan_path_str_rule,
    scan_project_path_relativity_rule,
    scan_rule_10,
)
from .tokens import code_only_content


def scan_python_antipatterns(
    path: Path, content: str, project_root: Path | None = None
) -> list[RuleFinding]:
    lines = content.splitlines()
    code_only = code_only_content(content)
    code_lines = code_only.splitlines()
    findings = (
        scan_line_rules(path, lines, code_lines, project_root)
        + scan_rule_10(path, lines, code_only, project_root)
        + scan_path_str_rule(path, lines, code_lines, project_root)
        + scan_project_path_relativity_rule(path, lines, content, project_root)
        + scan_ast_rules(path, lines, content, project_root)
    )
    return sorted(findings, key=lambda finding: finding.line)


def scan_hook_payload(payload: JSONDict, project_root: Path) -> AntipatternReport:
    tool_input = tool_input_dict(payload)

    target_path = hook_target_relative_path(payload, project_root)
    if not target_path or not is_src_path(target_path) or not tool_input:
        return AntipatternReport(
            scope="none",
            scanned_paths=[],
            rule_findings=[],
            optional_arg_findings=[],
            omitted_notes=[],
        )

    full_content = "\n".join(extract_tool_input_contents(tool_input))
    if not full_content.strip():
        return AntipatternReport(
            scope="none",
            scanned_paths=[target_path],
            rule_findings=[],
            optional_arg_findings=[],
            omitted_notes=[],
        )

    findings = scan_python_antipatterns(target_path, full_content)

    return AntipatternReport(
        scope="hook-payload",
        scanned_paths=[target_path],
        rule_findings=findings,
        optional_arg_findings=[],
        omitted_notes=[],
    )


def scan_optional_arg_shims(_path: Path, _content: str) -> list[RuleFinding]:
    """Deprecated: use scan_optional_arg_shims_with_notes instead."""
    return []
