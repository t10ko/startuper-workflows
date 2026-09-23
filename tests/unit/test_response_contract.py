"""Pin the response contract's always-loaded size and its consolidation.

Twelve rounds of rule-tuning once grew the always-on response-shaping payload
past a hundred lines before it was consolidated into one short file whose
companion rule files were deleted. The ceiling below keeps that cut from
reopening: `response-contract.md` is re-injected on EVERY user turn by a
hook, so every line in it bills on every turn of every session.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / ".agents/rules/response-contract.md"

PER_TURN_LINE_CEILING = 20

# Companion rule files consolidated into response-contract.md. Their
# reintroduction would rebuild multi-file drift, and any new file that
# references them is referencing deleted instructions.
DELETED = (
    ".agents/rules/response-style.md",
    ".agents/rules/visual-response-format.md",
)


def test_response_contract_stays_under_the_per_turn_ceiling() -> None:
    content_lines = [
        line
        for line in CONTRACT.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(content_lines) <= PER_TURN_LINE_CEILING, (
        f"{CONTRACT.relative_to(ROOT)} has {len(content_lines)} content lines, "
        f"over the {PER_TURN_LINE_CEILING}-line ceiling; this file is "
        "re-injected on every user turn, so trim it rather than growing it"
    )


def test_the_companion_rule_files_stay_deleted() -> None:
    for path in DELETED:
        assert not (ROOT / path).exists(), (
            f"{path} was consolidated into response-contract.md; "
            "reintroducing it rebuilds multi-file response-format drift"
        )


def test_no_rule_still_references_the_deleted_files() -> None:
    for rule in (ROOT / ".agents/rules").glob("*.md"):
        text = rule.read_text(encoding="utf-8")
        for deleted in DELETED:
            name = Path(deleted).name
            assert name not in text, (
                f"{rule.relative_to(ROOT)} still references {name}, deleted "
                "in the consolidation"
            )
