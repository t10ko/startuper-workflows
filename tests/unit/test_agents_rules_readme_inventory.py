"""Pin that .agents/rules/README.md's inventory matches the rules on disk,
and that the single-source pointers it makes resolve."""

from __future__ import annotations

import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = ROOT / ".agents/rules"

# README.md points at (module, constant) pairs instead of restating the sets
# they own. A pointer is worth exactly as much as its ability to resolve, so
# these names -- and only these -- are what the pointer test holds README to.
PROJECTION_SET_POINTERS = (
    ("tests.unit.test_claude_projection", "CLAUDE_RULES_EXCLUDED", "projection exclusion set"),
    (
        "tests.unit.test_claude_rules_payload_budget",
        "EXPECTED_DEFERRED_RULE_GLOBS",
        "deferred-rule set",
    ),
)


def _documented_rule_files() -> set[str]:
    readme_text = (RULES_DIR / "README.md").read_text(encoding="utf-8")
    documented = set()
    for line in readme_text.splitlines():
        if not line.startswith("- "):
            continue
        start = line.find("`")
        end = line.find("`", start + 1)
        if start == -1 or end == -1:
            continue
        filename = line[start + 1 : end]
        if filename.endswith(".md"):
            documented.add(filename)
    return documented


def test_readme_bullet_list_matches_rule_files_on_disk() -> None:
    actual_files = {
        path.name for path in RULES_DIR.glob("*.md") if path.name != "README.md"
    }
    assert _documented_rule_files() == actual_files


def test_readme_set_pointers_resolve() -> None:
    """Each (module, constant) pointer README makes must resolve, be named in
    README exactly once, and that mention must sit in the same block as the
    constant's name — so a moved module or renamed constant fails loudly
    instead of leaving README pointing at nothing."""
    readme_text = (RULES_DIR / "README.md").read_text(encoding="utf-8")
    blocks = [" ".join(block.split()) for block in readme_text.split("\n\n") if block.strip()]

    for module_name, constant, label in PROJECTION_SET_POINTERS:
        module = importlib.import_module(module_name)
        assert hasattr(module, constant), (
            f"README's {label} pointer names {module_name}.{constant}, which "
            "does not exist -- move the pointer or restore the constant"
        )
        mentions = [block for block in blocks if module_name.rsplit(".", 1)[-1] in block]
        assert len(mentions) == 1, (
            f"the test module holding the {label} ({module_name}) must be "
            f"named exactly once in rules/README.md, found {len(mentions)}"
        )
        assert constant in mentions[0], (
            f"README names the {label} module but not its constant "
            f"{constant} in the same block"
        )
