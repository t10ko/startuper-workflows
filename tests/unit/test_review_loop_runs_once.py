"""The deep code review runs once, at the very end, over the whole combined diff.

Two different activities were both called "review": a cheap per-group acceptance
gate against criteria the plan already wrote down, and `code-review-fix-loop`,
which re-reads the entire diff. The collision made "one per group" and "only once
at the end" both look true. These tests pin the separation and the single run.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOOP_SKILL = REPO / ".agents/skills/code-review-fix-loop/SKILL.md"
LANDING = (
    REPO
    / ".agents/skills/parallel-subagent-driven-development/references/landing-and-pr.md"
)
DISPATCH = (
    REPO
    / ".agents/skills/parallel-subagent-driven-development/references/dispatch-and-briefs.md"
)


def _single_line(path: Path) -> str:
    return re.sub(r"\s+", " ", path.read_text())


def test_skill_description_carries_the_once_invariant() -> None:
    """The description is all an orchestrator reads before deciding to invoke it."""
    description = (
        _single_line(LOOP_SKILL).split("description:")[1].split("disable-model")[0]
    )

    assert "RUNS EXACTLY ONCE PER BODY OF WORK, AT THE VERY END" in description
    for split in ("never per task", "never per task group", "never per worktree"):
        assert split in description, f"description must rule out {split!r}"
    assert "never a second time" in description


def test_skill_body_forbids_every_partial_run() -> None:
    body = _single_line(LOOP_SKILL)

    assert "Run this once, at the very end, over everything combined" in body
    assert "never once per worktree, never once per wave" in body
    assert "cannot be seen at all until they are combined" in body


def test_landing_owns_when_the_loop_runs() -> None:
    body = _single_line(LANDING)

    assert "the only `code-review-fix-loop` run of the entire workflow" in body
    assert "this file is the single owner of when it runs" in body
    assert "Every earlier step is forbidden from dispatching it" in body


def test_dispatch_separates_the_acceptance_gate_from_the_code_review() -> None:
    body = _single_line(DISPATCH)

    assert 'Two different things are called "review"' in body
    assert "It is not a code review." in body
    assert (
        "Nothing in Step 2 may dispatch `code-review-fix-loop`, for any reason." in body
    )


def test_no_step_before_landing_dispatches_the_loop() -> None:
    """A prohibition may name the dispatch; an instruction to perform it may not."""
    negations = ("never", "not", "nothing", "no ", "forbidden", "only")
    offending = [
        sentence
        for sentence in _single_line(DISPATCH).split(". ")
        if "dispatch `code-review-fix-loop`" in sentence
        and not any(word in sentence.lower() for word in negations)
    ]

    assert offending == [], (
        f"dispatch-and-briefs.md instructs a loop dispatch: {offending}"
    )
