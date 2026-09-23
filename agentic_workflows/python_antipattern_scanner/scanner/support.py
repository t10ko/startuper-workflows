from __future__ import annotations

from pathlib import Path

from agentic_workflows.python_antipattern_scanner.models import RuleDefinition, RuleFinding
from agentic_workflows.python_antipattern_scanner.rules import ALLOW_COMMENT

BOUNDARY_COMMENT = "LEGIT_BOUNDARY"


def relative_path(path: Path, project_root: Path | None) -> Path:
    return path.relative_to(project_root) if project_root else path


def line_evidence(lines: list[str], lineno: int) -> str:
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].strip()
    return ""


def append_rule_finding(
    findings: list[RuleFinding],
    seen: set[tuple[str, int, str]],
    path: Path,
    project_root: Path | None,
    lineno: int,
    definition: RuleDefinition,
    evidence: str,
) -> None:
    if not evidence or ALLOW_COMMENT in evidence:
        return
    key = (definition.rule_id, lineno, evidence)
    if key in seen:
        return
    seen.add(key)
    findings.append(
        RuleFinding(
            path=relative_path(path, project_root),
            line=lineno,
            rule_id=definition.rule_id,
            message=definition.message,
            evidence=evidence,
            why=definition.why,
            best_fix=definition.best_fix,
            group_title=definition.group_title,
        )
    )


def skip_line_rule(line: str, rule_id: str) -> bool:
    if ALLOW_COMMENT in line:
        return True
    boundary_rule_ids = {"RULE_1", "RULE_14", "RULE_15"}
    return rule_id in boundary_rule_ids and BOUNDARY_COMMENT in line
