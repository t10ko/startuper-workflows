from __future__ import annotations

from pathlib import Path

from .jscpd_runner import (
    DEFAULT_MIN_LINES,
    DEFAULT_MIN_TOKENS,
    DuplicationScanError,
    run_jscpd,
)
from .models import DuplicationReport
from .report_builder import parse_jscpd_report
from .scope import bounded_scan_paths


def _relative(path: Path, resolved_root: Path) -> Path:
    return (
        path.relative_to(resolved_root) if path.is_relative_to(resolved_root) else path
    )


def build_duplication_report(
    *,
    project_root: Path,
    touched_paths: list[Path],
    jscpd_output_dir: Path,
    scope: str = "code-review-fix-loop",
    min_tokens: int = DEFAULT_MIN_TOKENS,
    min_lines: int = DEFAULT_MIN_LINES,
) -> DuplicationReport:
    """REQ-005/007/014: expand touched paths to the bounded scan corpus,
    run jscpd once over it, and parse the result into stable-ID
    candidates. Never raises for a scanner failure -- returns a
    DuplicationReport with `skipped_reason` set instead, so the
    coordinator can report the skip explicitly (per the spec's
    error/recovery flow) rather than crashing the review loop or
    silently falling back to LLM-only judgment."""
    resolved_root = project_root.resolve()
    scan_paths = bounded_scan_paths(project_root, touched_paths)
    npx_cwd = resolved_root / "src-ui"

    try:
        report_path = run_jscpd(
            scan_paths,
            output_dir=jscpd_output_dir,
            npx_cwd=npx_cwd,
            min_tokens=min_tokens,
            min_lines=min_lines,
        )
        candidates = parse_jscpd_report(report_path, project_root)
    except DuplicationScanError as exc:
        return DuplicationReport(
            scope=scope,
            scanned_paths=[_relative(path, resolved_root) for path in scan_paths],
            candidates=[],
            skipped_reason=str(exc),
        )

    return DuplicationReport(
        scope=scope,
        scanned_paths=[_relative(path, resolved_root) for path in scan_paths],
        candidates=candidates,
        skipped_reason=None,
    )


def render_markdown_report(report: DuplicationReport) -> str:
    lines = [
        "# Duplication Scan Report",
        "",
        "## Snapshot",
        f"- **Scope:** `{report.scope}`",
        f"- **Files Scanned:** {len(report.scanned_paths)}",
        f"- **Duplicate Candidates Found:** {len(report.candidates)}",
        "",
        "## Scanned Paths",
        "",
    ]
    lines.extend(f"- `{path.as_posix()}`" for path in report.scanned_paths)
    lines.append("")

    if report.skipped_reason is not None:
        lines.append("## SKIPPED")
        lines.append("")
        lines.append(
            f"D-C's scanner did not run this iteration: {report.skipped_reason}"
        )
        lines.append(
            "The coordinator MUST treat D-C as skipped for this iteration -- "
            "never fall back to LLM-only duplication judgment."
        )
        lines.append("")
        return "\n".join(lines)

    if not report.candidates:
        lines.append("## Candidates")
        lines.append("")
        lines.append("No duplicate candidates found in the scanned scope.")
        lines.append("")
        return "\n".join(lines)

    lines.append("## Candidates")
    lines.append("")
    for candidate in report.candidates:
        lines.append(f"### {candidate.candidate_id}")
        lines.append("")
        lines.append(f"- **Format:** `{candidate.format}`")
        lines.append(f"- **Lines:** {candidate.lines}")
        lines.append(f"- **Tokens:** {candidate.tokens}")
        lines.append(
            f"- **First:** `{candidate.first.path.as_posix()}:"
            f"{candidate.first.start_line}-{candidate.first.end_line}`"
        )
        lines.append(
            f"- **Second:** `{candidate.second.path.as_posix()}:"
            f"{candidate.second.start_line}-{candidate.second.end_line}`"
        )
        lines.append(f"- **Fragment:**\n```\n{candidate.fragment}\n```")
        lines.append("")

    return "\n".join(lines)
