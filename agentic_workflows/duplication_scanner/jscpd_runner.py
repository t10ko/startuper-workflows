from __future__ import annotations

import subprocess
from pathlib import Path

BIN_NPX = "npx"
from agentic_workflows.exceptions import EnvironmentFaultError
from agentic_workflows.process_runner import run_safe_process

DEFAULT_MIN_TOKENS = 50
DEFAULT_MIN_LINES = 5
DEFAULT_TIMEOUT_SECONDS = 120.0
JSCPD_REPORT_FILENAME = "jscpd-report.json"


class DuplicationScanError(RuntimeError):
    """Raised when jscpd cannot be run or fails to produce a usable report.

    The coordinator (`code-review-fix-loop` Step 2) treats this as
    dimension 11 being skipped for the current loop iteration -- never a
    silent fallback to LLM-only duplication judgment (spec's error/
    recovery flow, REQ-005)."""


def run_jscpd(
    scan_paths: list[Path],
    *,
    output_dir: Path,
    npx_cwd: Path,
    min_tokens: int = DEFAULT_MIN_TOKENS,
    min_lines: int = DEFAULT_MIN_LINES,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Path:
    """Run `npx jscpd` (resolved against `npx_cwd`'s local devDependency,
    i.e. `src-ui/`, per `src-ui/package.json`) over scan_paths, writing
    `jscpd-report.json` under output_dir. Returns the path to that report.

    Never lets a missing binary, non-zero exit, missing report, or hung
    process escape as an unhandled crash -- always raises
    DuplicationScanError instead (REQ-005/REQ-014; Q-002's residual risk
    of no fixed timeout budget is resolved here with a documented
    `timeout` default, overridable by the caller)."""
    if not scan_paths:
        raise DuplicationScanError("No paths to scan for duplication.")

    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        BIN_NPX,
        "jscpd",
        "--silent",
        "--reporters",
        "json",
        "--absolute",
        "--min-tokens",
        str(min_tokens),
        "--min-lines",
        str(min_lines),
        "--output",
        str(output_dir),
        *[path.as_posix() for path in scan_paths],
    ]
    try:
        completed = run_safe_process(
            command,
            cwd=str(npx_cwd),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except EnvironmentFaultError as exc:
        raise DuplicationScanError(f"jscpd is not available: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise DuplicationScanError(
            f"jscpd timed out after {timeout}s scanning {len(scan_paths)} path(s)."
        ) from exc

    report_path = output_dir / JSCPD_REPORT_FILENAME
    if not report_path.exists():
        raise DuplicationScanError(
            f"jscpd exited {completed.returncode} without producing "
            f"{JSCPD_REPORT_FILENAME} in {output_dir}: {completed.stderr.strip()}"
        )
    return report_path
