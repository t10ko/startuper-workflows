"""Pin the frontmatter invariants that keep every skill loadable in ZCode.

Discovered 2026-09-13 in the origin repo: ZCode's skill loader drops a skill
outright when its frontmatter ``description`` exceeds 1024 characters, while
Claude Code has no such limit — one skill sat at 1687 and was silently absent
from ZCode's registry, making the SDD workflow's Step 7 skill uninvokable in
one harness with no error anywhere. Every skill must also carry a ``name``
matching its directory, and the progress-report skill must stay the single
owner of the bar spec.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / ".agents" / "skills"
PROGRESS_REPORT = SKILLS / "progress-report" / "SKILL.md"
SDD_DIR = SKILLS / "parallel-subagent-driven-development"

#: ZCode's frontmatter loader drops a skill whose description exceeds this;
#: Claude Code has no such limit, so nothing in this repo may exceed it.
MAX_DESCRIPTION_CHARS = 1024

_NAME = re.compile(r"^name:\s*(?P<text>.*)$", re.MULTILINE)
_DESCRIPTION = re.compile(r"^description:\s*(?P<text>.*)$", re.MULTILINE)


def _frontmatter(path: Path) -> str:
    """The YAML frontmatter block between the opening and closing ``---``."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines and lines[0].strip() == "---", f"{path} has no frontmatter block"
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index])
    raise AssertionError(f"{path} has an unterminated frontmatter block")


def _description(path: Path) -> str:
    match = _DESCRIPTION.search(_frontmatter(path))
    assert match, f"{path} has no description in its frontmatter"
    return match.group("text").strip()


def _name(path: Path) -> str:
    match = _NAME.search(_frontmatter(path))
    assert match, f"{path} has no name in its frontmatter"
    return match.group("text").strip()


def test_every_skill_has_frontmatter_fields_that_load_in_both_harnesses() -> None:
    skill_files = sorted(SKILLS.glob("*/SKILL.md"))
    assert skill_files, "no skills found"

    problems: dict[str, str] = {}
    for path in skill_files:
        relative = str(path.relative_to(ROOT))
        try:
            name = _name(path)
            description = _description(path)
        except AssertionError as error:
            problems[relative] = str(error)
            continue
        if not name:
            problems[relative] = "empty name"
        elif name != path.parent.name:
            problems[relative] = f"name {name!r} does not match its directory"
        elif len(description) > MAX_DESCRIPTION_CHARS:
            problems[relative] = (
                f"description is {len(description)} chars; over "
                f"{MAX_DESCRIPTION_CHARS} is dropped silently by ZCode's "
                "skill loader"
            )

    assert problems == {}, problems


def test_progress_report_skill_exists_and_describes_its_trigger() -> None:
    description = _description(PROGRESS_REPORT)
    assert len(description) <= MAX_DESCRIPTION_CHARS
    lowered = description.lower()
    assert "progress" in lowered
    assert "bar" in lowered


def test_progress_report_is_the_single_owner_of_the_bar_spec() -> None:
    """No workflow file may carry a copy of the bar math; they invoke the skill."""
    spec = PROGRESS_REPORT.read_text(encoding="utf-8")
    assert "Exact Character Calculation" in spec

    for document in sorted(SDD_DIR.rglob("*.md")):
        assert "Exact Character Calculation" not in document.read_text(
            encoding="utf-8"
        ), (
            f"{document} carries a copy of the progress-bar spec that "
            "progress-report/SKILL.md owns"
        )

    assert not (SDD_DIR / "references" / "status-reporting.md").exists(), (
        "status-reporting.md was the pre-skill copy of the bar spec; "
        "it must not come back"
    )


def test_sdd_skill_routes_step_four_through_the_progress_report_skill() -> None:
    body = " ".join((SDD_DIR / "SKILL.md").read_text(encoding="utf-8").split())
    assert "progress-report" in body
