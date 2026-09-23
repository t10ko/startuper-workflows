"""Cap the always-on rules payload and pin the deferred-rule glob set.

Claude Code reads every projected rule that declares no effective `paths:`
globs in full at session start. This module OWNS the deferred set (README's
pointer target): which rules are deferred, and behind which globs. It caps
the always-on byte total so the payload cannot creep back unnoticed, and
asserts every declared glob still reaches at least one real file — a glob
that matches nothing defers a rule into a black hole where no session can
ever load it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLAUDE_RULES_DIR = ROOT / ".claude/rules"
AGENTS_RULES_DIR = ROOT / ".agents/rules"

# Deliberately above the measured total (78,007 bytes across 15 files, at the
# standalone cut) but tight enough that adding an always-loaded rule fails
# loudly here instead of silently growing every session's cached prefix.
# Deferral is the lever: a new rule that only matters for certain files
# should declare `paths:` and land in EXPECTED_DEFERRED_RULE_GLOBS.
MAX_ALWAYS_LOADED_BYTES = 90_000

# The single owner of the deferral set (`.agents/rules/README.md` points
# here). Keyed by rule filename; values are the rule's declared `paths:`
# globs, in declaration order. Claude Code defers the file until it reads a
# path matching any glob.
EXPECTED_DEFERRED_RULE_GLOBS: dict[str, list[str]] = {
    "clean-typing.md": ["**/*.py"],
    "deliver-closed-domains-to-producers.md": ["agentic_workflows/**"],
    "github-pr-api.md": [
        "agentic_workflows/github_client.py",
        "agentic_workflows/secret_scan.py",
        ".agents/skills/parallel-subagent-driven-development/**",
    ],
    "no-real-api-calls-in-tests.md": ["tests/**/*.py"],
    "no-unjustified-fallbacks.md": ["**/*.py"],
    "provider-schema-transport-fidelity.md": ["agentic_workflows/**"],
    "python-antipatterns.md": ["**/*.py"],
}

_PATHS_BLOCK = re.compile(r"^paths:\n((?:\s+- .*\n)+)", re.M)


def _declared_paths(text: str) -> list[str]:
    """The rule's declared `paths:` globs, or [] when it declares none."""
    match = _PATHS_BLOCK.search(text)
    if not match:
        return []
    globs = []
    for line in match.group(1).strip().splitlines():
        item = line.strip()
        if item.startswith("- "):
            item = item[2:]
        globs.append(item.strip().strip('"').strip("'"))
    return globs


def _rule_frontmatter_and_body(rule_path: Path) -> str:
    return rule_path.read_text(encoding="utf-8")


def test_deferred_set_matches_the_declared_frontmatter() -> None:
    for name, expected_globs in EXPECTED_DEFERRED_RULE_GLOBS.items():
        rule_path = AGENTS_RULES_DIR / name
        assert rule_path.is_file(), (
            f"{name} is in EXPECTED_DEFERRED_RULE_GLOBS but does not exist "
            "under .agents/rules -- update the set"
        )
        declared = _declared_paths(
            _rule_frontmatter_and_body(rule_path)
        )
        assert declared == expected_globs, (
            f"{name} declares paths {declared} but the owner set holds "
            f"{expected_globs}; one of them is stale, and README points at "
            "this set as the single source of it"
        )


def test_no_undeclared_deferral_or_unowned_declaration() -> None:
    for path in sorted(AGENTS_RULES_DIR.glob("*.md")):
        if path.name in ("README.md", "block-git-mutations.md"):
            continue
        declared = _declared_paths(_rule_frontmatter_and_body(path))
        if path.name in EXPECTED_DEFERRED_RULE_GLOBS:
            continue
        assert not declared, (
            f"{path.name} declares paths {declared} but is not in "
            "EXPECTED_DEFERRED_RULE_GLOBS -- a rule cannot defer without "
            "being owned by the set README points at"
        )


def test_every_declared_glob_reaches_at_least_one_real_file() -> None:
    for name, globs in EXPECTED_DEFERRED_RULE_GLOBS.items():
        for pattern in globs:
            matches = sorted(ROOT.glob(pattern))
            assert matches, (
                f"{name} defers behind glob {pattern!r}, which matches no "
                "file in this repository -- the rule can never load; fix the "
                "glob or retire the rule"
            )


def test_always_loaded_payload_stays_under_the_cap() -> None:
    total = 0
    for path in sorted(CLAUDE_RULES_DIR.glob("*.md")):
        if path.name in EXPECTED_DEFERRED_RULE_GLOBS:
            continue
        total += path.stat().st_size
    assert total <= MAX_ALWAYS_LOADED_BYTES, (
        f"the always-on rules payload is {total} bytes, over the "
        f"{MAX_ALWAYS_LOADED_BYTES}-byte cap; defer a rule behind `paths:` "
        "(and add it to EXPECTED_DEFERRED_RULE_GLOBS) or shrink the rules"
    )
