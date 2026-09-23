"""The settings.json merge installer, run against real temp target files.

The installer owns exactly the entries whose command references
`.agents/hooks/` or `.agents/rules/response-contract.md`, replaces (never
duplicates) them on re-install, keeps every foreign entry, unions
`permissions.deny`, and is a byte-for-byte no-op once merged.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / ".agents" / "scripts" / "install_settings_merge.py"
)
SOURCE_SETTINGS = Path(__file__).resolve().parents[2] / ".claude" / "settings.json"

FOREIGN_COMMAND = 'python3 "$CLAUDE_PROJECT_DIR/my-own-hooks/foreign.py"'


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("install_settings_merge", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _merge(module: ModuleType, source: Path, target: Path) -> None:
    argv = [
        "install_settings_merge.py",
        "--source",
        source.as_posix(),
        "--target",
        target.as_posix(),
    ]
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(sys, "argv", argv)
        assert module.main() == 0


def _owned_commands(settings: dict) -> list[str]:
    found = []
    for groups in settings.get("hooks", {}).values():
        for group in groups:
            for entry in group.get("hooks", []):
                command = str(entry.get("command", ""))
                if ".agents/hooks/" in command or ".agents/rules/" in command:
                    found.append(command)
    return found


def _target_with(target_path: Path, settings: dict) -> Path:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return target_path


def test_a_fresh_target_gets_every_owned_hook_event(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    module = _load_module()
    source = json.loads(SOURCE_SETTINGS.read_text(encoding="utf-8"))
    target_path = _target_with(tmp_path / ".claude" / "settings.json", {})

    _merge(module, SOURCE_SETTINGS, target_path)

    merged = json.loads(target_path.read_text(encoding="utf-8"))
    assert sorted(merged["hooks"]) == sorted(source["hooks"]), (
        "every hook event the source declares must land in a fresh target"
    )
    for event, groups in source["hooks"].items():
        assert merged["hooks"][event] == groups
    assert merged["permissions"]["deny"] == source["permissions"]["deny"]
    assert "settings merged into" in capsys.readouterr().out


def test_a_pre_existing_foreign_hook_survives_the_merge(tmp_path: Path):
    module = _load_module()
    foreign = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": FOREIGN_COMMAND}],
                }
            ]
        },
        "permissions": {"deny": ["Read(.env)"]},
    }
    target_path = _target_with(tmp_path / ".claude" / "settings.json", foreign)

    _merge(module, SOURCE_SETTINGS, target_path)

    merged = json.loads(target_path.read_text(encoding="utf-8"))
    foreign_entries = [
        entry
        for group in merged["hooks"]["PreToolUse"]
        for entry in group.get("hooks", [])
        if entry.get("command") == FOREIGN_COMMAND
    ]
    assert len(foreign_entries) == 1, "the foreign hook must be kept untouched"
    assert "Read(.env)" in merged["permissions"]["deny"]


def test_rerunning_the_merge_is_a_no_op(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    module = _load_module()
    target_path = _target_with(tmp_path / ".claude" / "settings.json", {})

    _merge(module, SOURCE_SETTINGS, target_path)
    first_text = target_path.read_text(encoding="utf-8")
    backups_after_first = sorted(p.name for p in target_path.parent.glob("*.bak.*"))

    _merge(module, SOURCE_SETTINGS, target_path)
    second_text = target_path.read_text(encoding="utf-8")
    backups_after_second = sorted(p.name for p in target_path.parent.glob("*.bak.*"))

    assert second_text == first_text, "re-merging must not change the file"
    assert "already merged" in capsys.readouterr().out
    assert backups_after_second == backups_after_first, (
        "the no-op re-merge must not write another backup"
    )


def test_owned_entries_from_a_previous_install_are_replaced_not_duplicated(
    tmp_path: Path,
):
    module = _load_module()
    source = json.loads(SOURCE_SETTINGS.read_text(encoding="utf-8"))
    target_path = _target_with(tmp_path / ".claude" / "settings.json", {})

    _merge(module, SOURCE_SETTINGS, target_path)

    # Simulate a stale previous install: an outdated owned entry (a duplicated
    # group carrying an owned command) left in the target. Stripping by marker
    # and re-appending must collapse all of it to exactly one copy of each
    # owned command from the current source.
    merged = json.loads(target_path.read_text(encoding="utf-8"))
    stale_group = {
        "matcher": "Bash",
        "hooks": [
            {
                "type": "command",
                "command": 'python3 "$CLAUDE_PROJECT_DIR/.agents/hooks/block_grep_search.py"',
            }
        ],
    }
    merged["hooks"]["PreToolUse"].append(stale_group)
    target_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")

    _merge(module, SOURCE_SETTINGS, target_path)

    final = json.loads(target_path.read_text(encoding="utf-8"))
    owned = _owned_commands(final)
    source_owned = _owned_commands(source)
    assert sorted(owned) == sorted(source_owned), (
        "every owned command must appear exactly once, from the current source"
    )


def test_permissions_deny_is_unioned_without_duplicates(tmp_path: Path):
    module = _load_module()
    source = json.loads(SOURCE_SETTINGS.read_text(encoding="utf-8"))
    source_deny = source["permissions"]["deny"]
    target_path = _target_with(
        tmp_path / ".claude" / "settings.json",
        {"permissions": {"deny": [source_deny[0], "Bash(rm -rf /)"]}},
    )

    _merge(module, SOURCE_SETTINGS, target_path)

    merged = json.loads(target_path.read_text(encoding="utf-8"))
    deny = merged["permissions"]["deny"]
    assert len(deny) == len(set(deny)), f"duplicates in deny: {deny}"
    for entry in [*source_deny, "Bash(rm -rf /)"]:
        assert entry in deny


def test_a_changed_target_gets_a_backup_of_its_previous_content(tmp_path: Path):
    module = _load_module()
    target_path = _target_with(
        tmp_path / ".claude" / "settings.json",
        {"permissions": {"deny": ["Bash(rm -rf /)"]}},
    )
    previous = target_path.read_text(encoding="utf-8")

    _merge(module, SOURCE_SETTINGS, target_path)

    backups = sorted(target_path.parent.glob("*.bak.*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == previous
