import pytest

from agentic_workflows.grep_search_guard import build_grep_block_message, find_bare_grep_segment


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("grep foo src/", True),
        ("grep -rn foo src/", True),
        ("egrep foo src/", True),
        ("fgrep foo src/", True),
        ("cd src && grep foo .", True),
        ("grep foo file1 file2 && echo done", True),
        ("FOO=1 grep foo file", True),
        ("env FOO=1 grep foo file", True),
        ("sudo grep foo file", True),
        # A qualified path names the same program: matched on basename, the
        # way `git_write_guard._head_is_git` already matches git.
        ("/usr/bin/grep foo src/", True),
        ("/bin/egrep foo src/", True),
        ("/usr/bin/fgrep foo src/", True),
        ("env /usr/bin/grep foo src/", True),
        ("sudo /usr/bin/grep foo src/", True),
        ("rg foo", False),
        ("rg foo src/", False),
        ("ps aux | grep node", False),
        ("history | grep foo", False),
        ("rg foo | grep bar", False),
        ("rg foo | grep bar | grep baz", False),
        ("find . -name '*.py' | xargs grep foo", False),
        ("git log --oneline", False),
    ],
)
def test_find_bare_grep_segment(command: str, expected: bool) -> None:
    assert (find_bare_grep_segment(command) is not None) is expected


def test_find_bare_grep_segment_returns_the_offending_segment_text() -> None:
    assert find_bare_grep_segment("cd src && grep -rn foo .") == "grep -rn foo ."


def test_find_bare_grep_segment_returns_none_on_unparseable_command() -> None:
    assert find_bare_grep_segment("echo 'unterminated") is None


def test_build_grep_block_message_is_none_for_allowed_command() -> None:
    assert build_grep_block_message("rg foo src/") is None


def test_build_grep_block_message_names_rg_and_the_blocked_segment() -> None:
    message = build_grep_block_message("grep -rn foo src/")
    assert message is not None
    assert "rg" in message
    assert "grep -rn foo src/" in message
