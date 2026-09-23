from __future__ import annotations

from pathlib import Path

from .models import AntipatternReport, OptionalArgFinding, RuleFinding
from .optional_arg_logic import scan_optional_arg_shims_with_notes
from .scanner import scan_python_antipatterns


def _iter_python_paths(project_root: Path, paths: list[Path]) -> list[Path]:
    scanned_paths: list[Path] = []
    for raw_path in paths:
        path = raw_path if raw_path.is_absolute() else project_root / raw_path
        if path.is_file() and path.suffix == ".py":
            scanned_paths.append(path)
            continue
        if path.is_dir():
            scanned_paths.extend(sorted(p for p in path.rglob("*.py") if p.is_file()))
    return sorted(set(scanned_paths))


def _build_report_from_paths(
    project_root: Path,
    scope: str,
    scanned_paths: list[Path],
) -> AntipatternReport:
    rule_findings: list[RuleFinding] = []
    optional_findings: list[OptionalArgFinding] = []
    omitted_notes: list[str] = []

    for path in scanned_paths:
        content = path.read_text(encoding="utf-8")
        rule_findings.extend(scan_python_antipatterns(path, content, project_root))
        res = scan_optional_arg_shims_with_notes(path, content)
        optional_findings.extend(
            [
                OptionalArgFinding(
                    path=finding.path.relative_to(project_root),
                    line=finding.line,
                    function_name=finding.function_name,
                    parameter_name=finding.parameter_name,
                    annotation=finding.annotation,
                    evidence=finding.evidence,
                    why=finding.why,
                    best_fix=finding.best_fix,
                )
                for finding in res.findings
            ]
        )
        omitted_notes.extend(res.omitted_notes)

    return AntipatternReport(
        scope=scope,
        scanned_paths=[path.relative_to(project_root) for path in scanned_paths],
        rule_findings=rule_findings,
        optional_arg_findings=optional_findings,
        omitted_notes=omitted_notes,
    )


def build_repo_antipattern_report(
    project_root: Path,
    scope: str = "src-tooling",
) -> AntipatternReport:
    targets = [
        project_root / "src",
        project_root / "scripts",
        project_root / ".agents" / "hooks",
        project_root / ".agents" / "skills",
    ]
    scanned_paths = _iter_python_paths(project_root, targets)
    return _build_report_from_paths(project_root, scope, scanned_paths)


def build_paths_antipattern_report(
    project_root: Path,
    paths: list[Path],
) -> AntipatternReport:
    scanned_paths = _iter_python_paths(project_root, paths)
    return _build_report_from_paths(project_root, "paths", scanned_paths)


def render_markdown_report(report: AntipatternReport) -> str:
    lines = [
        "# Python Antipattern Extraction Report",
        "",
        "## Snapshot",
        f"- **Scope:** `{report.scope}`",
        f"- **Files Scanned:** {len(report.scanned_paths)}",
        f"- **Antipatterns Found:** {len(report.rule_findings)}",
        f"- **Suspicious Optional Args:** {len(report.optional_arg_findings)}",
        "",
    ]

    if report.rule_findings:
        lines.append("## Confirmed Antipatterns")
        lines.append("")
        # Group by rule then file
        by_rule: dict[str, list[RuleFinding]] = {}
        for f in report.rule_findings:
            by_rule.setdefault(f.group_title or f.message, []).append(f)

        for title in sorted(by_rule.keys()):
            lines.append(f"### {title}")
            lines.append("")
            for f in by_rule[title]:
                lines.append(f"- `{f.path.as_posix()}:{f.line}`")
                lines.append(f"  - **Evidence:** `{f.evidence}`")
                lines.append(f"  - **Why:** {f.why}")
                lines.append(f"  - **Fix:** {f.best_fix}")
                lines.append("")

    if report.optional_arg_findings:
        lines.append("## Suspicious Optional Args")
        lines.append("")
        for f in report.optional_arg_findings:
            lines.append(f"### `{f.path.as_posix()}:{f.line}`")
            lines.append(f"- **Function:** `{f.function_name}`")
            lines.append(f"- **Param:** `{f.parameter_name}: {f.annotation}`")
            lines.append(f"- **Evidence:** `{f.evidence}`")
            lines.append(f"- **Why:** {f.why}")
            lines.append(f"- **Fix:** {f.best_fix}")
            lines.append("")

    if report.omitted_notes:
        lines.append("## Omitted / Ambiguous")
        lines.append("")
        lines.extend(f"- {note}" for note in report.omitted_notes)
        lines.append("")

    return "\n".join(lines)
