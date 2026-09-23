"""Block file-edit tools from writing agent-memory records without consent.

Claude Code's built-in auto-memory writes records through the ordinary
Write/Edit tools into `~/.claude/projects/<slug>/memory/`. Those writes need
no user approval, are untracked, and are auto-injected into every later
session — so a rule written there silently outranks repo skills while being
invisible to code review. A stale record written that way suppressed a
shipped workflow across three sessions before anyone noticed (see
`docs/decision-notes/2026-07-24-stale-memory-overrides-shipped-branch-pr-workflow.md`).

This guard denies those writes so memories land in tracked, reviewable repo
files instead, and only after the user explicitly agrees.
"""

from __future__ import annotations

from pathlib import Path

CLAUDE_DIR = ".claude"
PROJECTS_DIR = "projects"
MEMORY_DIR = "memory"
REMEMBER_DIR = ".remember"

# `.claude` / `projects` / <slug> / `memory` — the slug occupies exactly one
# segment between the two literal anchors.
_SLUG_OFFSET = 3


def is_agent_memory_path(file_path: Path | None) -> bool:
    """True when `file_path` targets an agent-memory store.

    Two stores match:

    - Claude Code auto-memory, `<home>/.claude/projects/<slug>/memory/...`,
      matched on the ordered adjacency `.claude` -> `projects` -> <any one
      segment> -> `memory`. Never matched on the slug (a sanitized cwd, which
      varies per machine, checkout, and worktree) nor on the filename (records
      may be named anything). Requiring `projects` directly after `.claude` is
      what stops a repo-local `.claude/` directory — which has no `projects/`
      child — from matching itself.
    - The `remember` plugin store, any `.remember/` directory.
    """
    if file_path is None:
        return False

    parts = file_path.parts

    if REMEMBER_DIR in parts:
        return True

    for index in range(len(parts) - _SLUG_OFFSET):
        if (
            parts[index] == CLAUDE_DIR
            and parts[index + 1] == PROJECTS_DIR
            and parts[index + _SLUG_OFFSET] == MEMORY_DIR
        ):
            return True

    return False


def build_memory_write_block_message(file_path: Path | None) -> str | None:
    """Return a user-facing block reason for an agent-memory write, or None."""
    if not is_agent_memory_path(file_path):
        return None

    return (
        "Blocked an un-consented agent-memory write. Memory must be recorded "
        "deliberately: ask the user with AskUserQuestion, and only on an "
        "explicit yes record it in a tracked repo file — `.agents/rules/` for "
        "a standing rule, `MEMORIES.md` for a terse one, "
        "`.agents/open-gaps.md` for an unfixed issue. Never write to "
        "`~/.claude/**/memory/` or `.remember/`: both are untracked, "
        "per-machine, and invisible to code review. "
        "See .agents/rules/memory-consent.md."
    )
