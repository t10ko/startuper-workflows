from __future__ import annotations

from .jscpd_runner import (
    DEFAULT_MIN_LINES,
    DEFAULT_MIN_TOKENS,
    DuplicationScanError,
    run_jscpd,
)
from .models import DuplicateCandidate, DuplicateOccurrence, DuplicationReport
from .report_builder import parse_jscpd_report
from .reporting import build_duplication_report, render_markdown_report
from .scope import DEFAULT_MAX_SIBLINGS_PER_DIRECTORY, bounded_scan_paths

__all__ = [
    "DEFAULT_MAX_SIBLINGS_PER_DIRECTORY",
    "DEFAULT_MIN_LINES",
    "DEFAULT_MIN_TOKENS",
    "DuplicateCandidate",
    "DuplicateOccurrence",
    "DuplicationReport",
    "DuplicationScanError",
    "bounded_scan_paths",
    "build_duplication_report",
    "parse_jscpd_report",
    "render_markdown_report",
    "run_jscpd",
]
