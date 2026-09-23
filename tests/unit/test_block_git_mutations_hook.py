"""Exercise the `.agents/hooks/block_git_mutations.py` PreToolUse hook end to
end. The hook itself lives outside `agentic_workflows/` and had no direct test
before; this closes that gap for the security-critical push-authorization
path."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

HOOK_PATH = _REPO_ROOT / ".agents" / "hooks" / "block_git_mutations.py"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("block_git_mutations_hook", HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_push_to_main_is_blocked_with_specific_reason(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    hook = _load_hook()
    payload = json.dumps(
        {
            "tool_input": {"command": "git push -u origin HEAD:main"},
            "cwd": "/some/where",
        }
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))

    with pytest.raises(SystemExit) as exc_info:
        hook.main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "push denied: cannot push to main" in captured.err


def test_unparseable_command_blocks_at_the_hook_with_a_parse_reason(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Only the hook proves fail-closed: a module returning a message is one
    step short of the process exiting 2. Any other exit code is a *non-blocking*
    error to `PreToolUse`, which lets the command run."""
    hook = _load_hook()
    payload = json.dumps(
        {
            "tool_input": {"command": 'git status "unclosed'},
            "cwd": "/some/where",
        }
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))

    with pytest.raises(SystemExit) as exc_info:
        hook.main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "could not be parsed" in captured.err
    assert "git command" not in captured.err


def test_safe_command_produces_no_exit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    hook = _load_hook()
    payload = json.dumps(
        {"tool_input": {"command": "git status"}, "cwd": "/some/where"}
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))

    hook.main()

    captured = capsys.readouterr()
    assert captured.err == ""
