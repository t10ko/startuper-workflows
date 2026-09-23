from __future__ import annotations

from .common import extract_tool_input_contents, hook_target_relative_path
from .models import AntipatternReport, OptionalArgFinding, RuleFinding
from .optional_arg_logic import scan_optional_arg_shims
from .reporting import (
    build_paths_antipattern_report,
    build_repo_antipattern_report,
    render_markdown_report,
)
from .rules import ALLOW_COMMENT
from .scanner import scan_hook_payload, scan_python_antipatterns

__all__ = [
    "ALLOW_COMMENT",
    "AntipatternReport",
    "OptionalArgFinding",
    "RuleFinding",
    "build_paths_antipattern_report",
    "build_repo_antipattern_report",
    "extract_tool_input_contents",
    "hook_target_relative_path",
    "render_markdown_report",
    "scan_hook_payload",
    "scan_optional_arg_shims",
    "scan_python_antipatterns",
]
