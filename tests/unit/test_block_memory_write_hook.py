"""Exercise the `.agents/hooks/block_memory_write.py` PreToolUse hook end to
end. The hook lives outside `agentic_workflows/`, so a guard-module test alone
would not prove the wiring — stdin parsing, path extraction, and the exit-2
contract are where it can break."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

HOOK_PATH = _REPO_ROOT / ".agents" / "hooks" / "block_memory_write.py"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("block_memory_write_hook", HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_auto_memory_write_is_blocked_with_consent_guidance(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    hook = _load_hook()
    payload = json.dumps(
        {
            "tool_input": {
                "file_path": "/Users/x/.claude/projects/-Users-x-dev-vc/memory/f.md"
            }
        }
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))

    with pytest.raises(SystemExit) as exc_info:
        hook.main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "memory-consent.md" in captured.err


def test_repo_local_claude_write_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The repo's own `.claude/` directory must not self-match through the real
    wiring — not just in the pure predicate."""
    hook = _load_hook()
    payload = json.dumps(
        {
            "tool_input": {
                "file_path": "/Users/x/dev/startuper-workflows/.claude/settings.json"
            }
        }
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))

    hook.main()

    captured = capsys.readouterr()
    assert captured.err == ""
