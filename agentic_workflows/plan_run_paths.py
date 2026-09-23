"""Where a plan run's authorization record lives on disk.

Split out of `plan_run_state` so a guard can name that location without paying
for the record's *writer*: `plan_run_state` imports `file_io`, which imports
this project's logger and configuration stack. Measured on this tree,
`import src.utils.plan_run_state` costs 1.11s against a 0.04s interpreter
baseline, while this module and `git_internals_edit_guard` together stay at
0.10s. That difference is charged to every single `Edit`/`Write` a session
makes, and a `PreToolUse` guard that fails closed on an import error would
turn any breakage anywhere in that stack into a repository-wide edit block.

`RUNS_DIR` has exactly one definition, here, naming the run-artifact root as
the single owner of that path (`.agents/rules/single-source-of-truth.md`).
`PLAN_RUNS_DIR` derives from it rather than restating the path. `plan_run_state`
imports both: `RUNS_DIR` to derive `LEGACY_RUN_STATE_PATH`, and `PLAN_RUNS_DIR`
for `record_path_for_branch`'s default; both are re-exported for the readers
that already import them from there.
"""

from __future__ import annotations

from pathlib import Path

# Root of every run-scoped artifact this repository tracks, in the main
# working tree — never inside a group's worktree or the integration worktree.
RUNS_DIR = Path("docs/runs")

# Run-scoped, one file per run.
PLAN_RUNS_DIR = RUNS_DIR / "plan-runs"
