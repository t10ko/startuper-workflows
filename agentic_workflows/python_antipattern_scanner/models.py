from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from agentic_workflows.types import JSONDict


@dataclass(frozen=True, slots=True)
class RuleDefinition:
    rule_id: str
    group_title: str
    message: str
    why: str
    best_fix: str


@dataclass(frozen=True, slots=True)
class RuleFinding:
    path: Path
    line: int
    rule_id: str
    message: str
    evidence: str
    why: str
    best_fix: str
    group_title: str = ""

    def as_dict(self) -> JSONDict:
        return {
            "path": self.path.as_posix(),
            "line": self.line,
            "rule_id": self.rule_id,
            "message": self.message,
            "evidence": self.evidence,
            "why": self.why,
            "best_fix": self.best_fix,
            "group_title": self.group_title,
        }


@dataclass(frozen=True, slots=True)
class OptionalArgFinding:
    path: Path
    line: int
    function_name: str
    parameter_name: str
    annotation: str
    evidence: str
    why: str
    best_fix: str

    def as_dict(self) -> JSONDict:
        return {
            "path": self.path.as_posix(),
            "line": self.line,
            "function_name": self.function_name,
            "parameter_name": self.parameter_name,
            "annotation": self.annotation,
            "evidence": self.evidence,
            "why": self.why,
            "best_fix": self.best_fix,
            "rule_id": "RULE_18",
            "message": "Suspicious Optional Arguments Repaired Inside Function",
            "group_title": "18. Suspicious Optional Arguments Repaired Inside Function",
        }


@dataclass(frozen=True, slots=True)
class OptionalArgScanResult:
    findings: list[OptionalArgFinding]
    omitted_notes: list[str]


@dataclass(frozen=True, slots=True)
class LineRule:
    definition: RuleDefinition
    pattern: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class OptionalRepairMatch:
    line: int
    evidence: str


@dataclass(frozen=True, slots=True)
class AntipatternReport:
    scope: str
    scanned_paths: list[Path]
    rule_findings: list[RuleFinding]
    optional_arg_findings: list[OptionalArgFinding]
    omitted_notes: list[str]

    @property
    def optional_findings(self) -> list[OptionalArgFinding]:
        return self.optional_arg_findings
