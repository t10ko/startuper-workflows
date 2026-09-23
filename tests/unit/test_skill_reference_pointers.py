"""Pin the reference-pointer contract every skill's SKILL.md must honor.

Content moved out of an always-loaded SKILL.md body into
`references/<topic>.md` stays reachable only if the pointer target exists on
disk, and the two named oversized skills' pointers must each state the
mandatory condition under which reading them is required rather than merely
advisory — plus those two files must fit the always-loaded byte budget.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_MAX_ALWAYS_LOADED_BYTES = 30_000

_OVERSIZED_SKILL_FILES = (
    ".agents/skills/task-spec/SKILL.md",
    ".agents/skills/parallel-subagent-driven-development/SKILL.md",
)

_REFERENCE_POINTER_PATH = re.compile(r"\.agents/skills/[\w.-]+/references/[\w.-]+\.md")

_TRIGGER_WINDOW_CHARS = 160


def _collapsed_whitespace(text: str) -> str:
    return " ".join(text.split())


def test_every_reference_pointer_target_exists_on_disk() -> None:
    skill_files = sorted((ROOT / ".agents/skills").glob("*/SKILL.md"))
    assert skill_files, "every skill SKILL.md file disappeared"

    checked_paths: set[str] = set()
    for skill_file in skill_files:
        text = skill_file.read_text(encoding="utf-8")
        checked_paths.update(_REFERENCE_POINTER_PATH.findall(text))

    assert checked_paths, "no references/*.md pointer found repo-wide"
    for relative_path in sorted(checked_paths):
        target = ROOT / relative_path
        assert target.is_file(), (
            f"a SKILL.md pointer names {relative_path}, which does not exist "
            "on disk -- the workflow must fail loudly here, not proceed "
            "without the instruction"
        )


def test_named_oversized_skill_files_state_a_mandatory_trigger_per_pointer() -> None:
    for skill_relpath in _OVERSIZED_SKILL_FILES:
        text = _collapsed_whitespace((ROOT / skill_relpath).read_text(encoding="utf-8"))
        matches = list(_REFERENCE_POINTER_PATH.finditer(text))
        assert matches, f"{skill_relpath} names no references/*.md pointer"
        for match in matches:
            window = text[match.end() : match.end() + _TRIGGER_WINDOW_CHARS].lower()
            assert "read it when" in window, (
                f"{skill_relpath} points at {match.group(0)} without a "
                "mandatory 'read it when' trigger in the same sentence "
                "('read it when drafting' is a mandatory trigger, not advice)"
            )


def test_named_oversized_skill_files_are_at_or_under_the_byte_budget() -> None:
    for skill_relpath in _OVERSIZED_SKILL_FILES:
        size = (ROOT / skill_relpath).stat().st_size
        assert size <= _MAX_ALWAYS_LOADED_BYTES, (
            f"{skill_relpath} is {size} bytes, over the "
            f"{_MAX_ALWAYS_LOADED_BYTES}-byte always-loaded budget"
        )
