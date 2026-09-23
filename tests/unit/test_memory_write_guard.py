from pathlib import Path

import pytest

from agentic_workflows.memory_write_guard import (
    build_memory_write_block_message,
    is_agent_memory_path,
)

MEMORY_DIR = "/Users/x/.claude/projects/-Users-x-dev-vc/memory"
REPO = "/Users/x/dev/example-project"


@pytest.mark.parametrize(
    ("file_path", "expected"),
    [
        # Claude Code auto-memory store: records, the index, nesting, the dir itself.
        (f"{MEMORY_DIR}/feedback_foo.md", True),
        (f"{MEMORY_DIR}/MEMORY.md", True),
        (f"{MEMORY_DIR}/sub/deep.md", True),
        (MEMORY_DIR, True),
        # Another project's slug is still a memory store — cross-project writes deny.
        ("/Users/x/.claude/projects/-other-project/memory/x.md", True),
        # The `remember` plugin store, anywhere.
        (f"{REPO}/.remember/now.md", True),
        # A repo-local `.claude/` must never self-match: it has no `projects/` child.
        (f"{REPO}/.claude/settings.json", False),
        (f"{REPO}/.claude/hooks/block_memory_write.py", False),
        # `.claude/projects/<slug>/` but not a memory directory.
        ("/Users/x/.claude/projects/-Users-x-dev-vc/other/x.md", False),
        # A normal repo file that merely has "memory" in its name.
        (f"{REPO}/src/utils/memory_write_guard.py", False),
        (None, False),
    ],
)
def test_is_agent_memory_path(file_path: str | None, expected: bool):
    resolved = Path(file_path) if file_path is not None else None
    assert is_agent_memory_path(resolved) is expected


def test_build_message_blocks_auto_memory_write():
    message = build_memory_write_block_message(Path(f"{MEMORY_DIR}/feedback_foo.md"))
    assert message is not None
    assert "memory-consent.md" in message


def test_build_message_blocks_remember_store_write():
    message = build_memory_write_block_message(Path(f"{REPO}/.remember/now.md"))
    assert message is not None


def test_build_message_allows_repo_files():
    assert (
        build_memory_write_block_message(Path(f"{REPO}/.claude/settings.json")) is None
    )


def test_build_message_allows_missing_path():
    assert build_memory_write_block_message(None) is None
