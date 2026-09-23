"""The hook scripts' runtime bootstrap, driven as real subprocesses.

Every `.agents/hooks/*.py` may be executed from ANY working directory (and
may itself be a symlink into a separate checkout of this repo): its bootstrap
must find `agentic_workflows` by walking up from the hook's own real location,
never from the process cwd. These tests execute the real hook file the way
the tool layer would — from a foreign cwd, and through a symlinked install —
so a bootstrap that only works from the repository root cannot pass.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK = REPO_ROOT / ".agents" / "hooks" / "block_grep_search.py"


def _run_hook(
    payload: object, *, cwd: Path, hook: Path = HOOK
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, hook.as_posix()],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd.as_posix(),
    )


def test_an_allowed_command_exits_zero_from_a_foreign_cwd(tmp_path: Path):
    done = _run_hook(
        {"tool_input": {"command": "rg -n 'pattern' src"}, "cwd": "/some/where"},
        cwd=tmp_path,
    )

    assert done.returncode == 0, done.stderr
    assert done.stderr == ""
    assert done.stdout == ""


def test_a_bare_grep_command_blocks_with_exit_two_from_a_foreign_cwd(tmp_path: Path):
    done = _run_hook(
        {"tool_input": {"command": "grep -r x ."}, "cwd": "/some/where"},
        cwd=tmp_path,
    )

    assert done.returncode == 2
    assert done.stderr.strip()


def test_the_bootstrap_finds_the_runtime_through_a_symlinked_install(tmp_path: Path):
    """The installed shape: `.agents` in a consumer repo is a symlink into a
    checkout of this repository. The hook file the tool layer executes is the
    symlink; the bootstrap must resolve it and find the runtime beside the
    REAL file, with the consumer repo containing no runtime of its own."""
    consumer = tmp_path / "consumer-repo"
    (consumer / ".agents" / "hooks").mkdir(parents=True)
    # No runtime of its own: the consumer carries only the symlink.
    installed_hook = consumer / ".agents" / "hooks" / "block_grep_search.py"
    installed_hook.symlink_to(HOOK)
    assert not (consumer / "agentic_workflows" / "__init__.py").exists()

    allowed = _run_hook(
        {"tool_input": {"command": "rg foo src/"}, "cwd": "/some/where"},
        cwd=tmp_path,
        hook=installed_hook,
    )
    blocked = _run_hook(
        {"tool_input": {"command": "grep -rn secret ."}, "cwd": "/some/where"},
        cwd=tmp_path,
        hook=installed_hook,
    )

    assert allowed.returncode == 0, allowed.stderr
    assert blocked.returncode == 2
    assert blocked.stderr.strip()
