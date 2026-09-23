"""Per-run state-record persistence for the branch/commit/push/PR workflow.

Each plan-execution "run" gets its own Markdown state file, path derived
from the run's branch name (never a single shared fixed path, to avoid
collision between concurrently running plans). The file is a fixed
`Label: value` header block (run status, branch, integration worktree,
verify-status commit SHA, secret-scan-clean commit SHA, PR URL, and a
terminal outcome) followed by free-form narrative text.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, TypedDict, Unpack

from agentic_workflows.file_io import write_text_atomic
from agentic_workflows.plan_run_paths import PLAN_RUNS_DIR, RUNS_DIR

LEGACY_RUN_STATE_PATH = RUNS_DIR / "parallel-run-state.md"

RunStatus = Literal["InProgress", "Finished"]

_HEADER_FIELDS = (
    ("Run status", "status"),
    ("Branch", "branch"),
    ("Integration worktree", "integration_worktree"),
    ("Verify-status SHA", "verify_status_sha"),
    ("Secret-scan-clean SHA", "secret_scan_clean_sha"),
    ("PR URL", "pr_url"),
    ("Terminal outcome", "terminal_outcome"),
)


@dataclass(frozen=True)
class PlanRunState:
    status: RunStatus
    branch: str
    integration_worktree: str
    verify_status_sha: str
    secret_scan_clean_sha: str
    pr_url: str
    terminal_outcome: str
    narrative: str = ""


def record_path_for_branch(branch: str, *, base_dir: Path = PLAN_RUNS_DIR) -> Path:
    """Run-scoped path derived from the branch name, every '/' flattened to
    '-' — never the legacy shared fixed path. e.g. branch 'plan/foo-bar' ->
    base_dir / 'plan-foo-bar.md'."""
    filename = branch.replace("/", "-")
    return base_dir / f"{filename}.md"


def _parse_status(value: str) -> RunStatus | None:
    if value == "InProgress":
        return "InProgress"
    if value == "Finished":
        return "Finished"
    return None


def parse_plan_run_state(text: str) -> PlanRunState | None:
    """Parse the fixed header block. Return None (fail closed) on ANY of:
    fewer lines than the header needs, a line not matching 'Label: value' or
    bare 'Label:' for the expected label at that position (order matters —
    the header fields appear in the exact order of _HEADER_FIELDS), or a
    status value that isn't exactly 'InProgress' or 'Finished'. Everything
    after the header lines becomes `narrative` (joined with '\\n'; empty
    string if there are no lines after the header)."""
    lines = text.removesuffix("\n").split("\n")
    if len(lines) < len(_HEADER_FIELDS):
        return None

    values: dict[str, str] = {}
    for index, (label, field_name) in enumerate(_HEADER_FIELDS):
        line = lines[index]
        prefix = f"{label}:"
        if line == prefix:
            value = ""
        elif line.startswith(f"{prefix} "):
            value = line[len(prefix) + 1 :]
        else:
            return None
        values[field_name] = value

    status = _parse_status(values["status"])
    if status is None:
        return None

    narrative = "\n".join(lines[len(_HEADER_FIELDS) :])

    return PlanRunState(
        status=status,
        branch=values["branch"],
        integration_worktree=values["integration_worktree"],
        verify_status_sha=values["verify_status_sha"],
        secret_scan_clean_sha=values["secret_scan_clean_sha"],
        pr_url=values["pr_url"],
        terminal_outcome=values["terminal_outcome"],
        narrative=narrative,
    )


def write_plan_run_state(path: Path, state: PlanRunState) -> Path:
    """Serialize `state` as the fixed header block (one 'Label: value' line
    per _HEADER_FIELDS, in order) followed by the narrative (if non-empty),
    written via write_text_atomic. Returns whatever write_text_atomic
    returns."""
    lines = [
        f"Run status: {state.status}",
        f"Branch: {state.branch}",
        f"Integration worktree: {state.integration_worktree}",
        f"Verify-status SHA: {state.verify_status_sha}",
        f"Secret-scan-clean SHA: {state.secret_scan_clean_sha}",
        f"PR URL: {state.pr_url}",
        f"Terminal outcome: {state.terminal_outcome}",
    ]
    if state.narrative:
        lines.extend(state.narrative.split("\n"))
    content = "\n".join(lines) + "\n"
    return write_text_atomic(path, content)


class PlanRunStateUpdate(TypedDict, total=False):
    """Sparse partial-update payload for `update_plan_run_state`, field for
    field identical to PlanRunState. Typing `status` as RunStatus (not
    `str`) makes an invalid status literal a static type error at the call
    site instead of a value that silently persists until the next parse."""

    status: RunStatus
    branch: str
    integration_worktree: str
    verify_status_sha: str
    secret_scan_clean_sha: str
    pr_url: str
    terminal_outcome: str
    narrative: str


def update_plan_run_state(
    path: Path, **field_updates: Unpack[PlanRunStateUpdate]
) -> PlanRunState:
    """Read the file at `path`, parse it, apply `field_updates` to produce a
    new PlanRunState (only the named fields change; everything else,
    including narrative, is preserved), write it back, and return the
    updated state. Raise ValueError with a message naming `path` if the
    existing file doesn't parse (parse_plan_run_state returns None) — never
    silently apply a mutation on top of an untrustworthy record."""
    existing = parse_plan_run_state(path.read_text(encoding="utf-8"))
    if existing is None:
        raise ValueError(f"cannot update unparsable plan run state at {path}")

    updated = replace(existing, **field_updates)
    write_plan_run_state(path, updated)
    return updated
