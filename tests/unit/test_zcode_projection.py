"""Pin the ZCode projection contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_zcode_skills_root_absent() -> None:
    zcode_skills_dir = ROOT / ".zcode/skills"
    assert not zcode_skills_dir.exists()
    assert not zcode_skills_dir.is_symlink()


def test_zcode_commands_is_symlink_to_agents_workflows() -> None:
    zcode_commands_dir = ROOT / ".zcode/commands"
    assert zcode_commands_dir.is_symlink()
    assert zcode_commands_dir.resolve() == (ROOT / ".agents/workflows").resolve()
