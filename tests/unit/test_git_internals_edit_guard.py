import json
import subprocess
import sys
from pathlib import Path

import pytest

from agentic_workflows.git_internals_edit_guard import (
    build_git_internals_edit_block_message,
    build_plan_run_record_edit_block_message,
    build_protected_edit_block_message,
    is_git_internals_path,
    is_plan_run_record_path,
)
from agentic_workflows.git_write_guard import (
    build_git_danger_block_message,
    is_git_dangerous_command,
)
from agentic_workflows.plan_run_state import (
    PlanRunState,
    record_path_for_branch,
    write_plan_run_state,
)

HOOK = (
    Path(__file__).resolve().parents[2]
    / ".agents"
    / "hooks"
    / "block_git_internals_edit.py"
)
BLOCK_EXIT_CODE = 2
PROTECTED_BRANCH = "sdd/atc-auth"


def _resolve_breaks_symlink_loops_silently(tmp_path: Path) -> bool:
    """Whether `Path.resolve()` resolves a symlink loop to a concrete path
    instead of raising. CPython 3.12 and earlier raise (`RuntimeError`/`OSError`),
    which the guard's fail-closed net converts to an undecidable-path refusal;
    from 3.13 `os.path.realpath(strict=False)` breaks the loop silently and
    returns the path as written. Allowing the path then is safe: the kernel
    refuses any write through the loop with ELOOP, so the honest verdict is
    "decidable, outside the class"."""
    (tmp_path / "probe-a").symlink_to(tmp_path / "probe-b")
    (tmp_path / "probe-b").symlink_to(tmp_path / "probe-a")
    try:
        (tmp_path / "probe-a" / "config").resolve()
    except OSError:
        return False
    return True


def _volume_is_case_insensitive(root: Path) -> bool:
    """Whether `root`'s volume aliases two spellings of one name. This
    repository's own checkout sits on such a volume; a temporary directory may
    not, and the tests below must be meaningful on either."""

    (root / "CaseProbe").mkdir()
    return (root / "caseprobe").exists()


def _run_hook(
    payload: object, process_cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Drive the real hook script the way `PreToolUse` does. Exit code 2 blocks
    the tool call; every other code — 1 included — lets it proceed.

    `process_cwd` is the directory the hook process itself is started in, which
    is not the same fact as the working directory the payload reports and must
    never decide the verdict."""

    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, HOOK.as_posix()],
        input=raw,
        capture_output=True,
        text=True,
        check=False,
        cwd=None if process_cwd is None else process_cwd.as_posix(),
    )


@pytest.mark.parametrize(
    ("file_path", "expected"),
    [
        ("/repo/.git/config", True),
        ("/repo/.git/worktrees/agent-1/config.worktree", True),
        ("/repo/.git/worktrees/agent-1/gitdir", True),
        ("/repo/.git/hooks/pre-commit", True),
        ("/repo/.git/HEAD", True),
        ("/repo/.git/refs/heads/main", True),
        ("/repo/.git/objects/ab/cdef", True),
        ("/repo/.git/info/exclude", True),
        ("/repo/.agents.worktrees/wt/.git", True),
        ("/repo/src/utils/config.py", False),
        ("/repo/books/my-book/config.json", False),
        ("/repo/.github/workflows/ci.yml", False),
        ("/repo/.gitignore", False),
        (None, False),
    ],
)
def test_is_git_internals_path(file_path: str | None, expected: bool):
    resolved = Path(file_path) if file_path is not None else None
    assert is_git_internals_path(resolved) is expected


def test_worktree_pointer_file_rewrite_is_refused(tmp_path: Path):
    """EC-002: rewriting a linked worktree's own `.git` pointer file re-points
    the ownership anchor every later authorization decision is made against."""

    main = tmp_path / "main"
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    attacker = main / ".agents.worktrees" / "wt"
    attacker.mkdir(parents=True)
    pointer = attacker / ".git"
    pointer.write_text(
        f"gitdir: {(main / '.git' / 'worktrees' / 'wt').as_posix()}\n",
        encoding="utf-8",
    )

    forged = tmp_path / "forged"
    (forged / ".git" / "worktrees" / "victim").mkdir(parents=True)
    victim = forged / ".agents.worktrees" / "victim"
    victim.mkdir(parents=True)
    (victim / ".git").write_text(
        f"gitdir: {(forged / '.git' / 'worktrees' / 'victim').as_posix()}\n",
        encoding="utf-8",
    )

    command = f"git -C {victim.as_posix()} reset --hard"
    assert is_git_dangerous_command(command, cwd=attacker) is True

    pointer.write_text(
        f"gitdir: {(forged / '.git' / 'worktrees' / 'victim').as_posix()}\n",
        encoding="utf-8",
    )
    assert is_git_dangerous_command(command, cwd=attacker) is False

    assert build_git_internals_edit_block_message(pointer) is not None


def test_symlink_into_the_administrative_area_is_refused(tmp_path: Path):
    """A path whose written form names nothing administrative but whose
    resolved form lands inside `.git`."""

    (tmp_path / ".git").mkdir()
    (tmp_path / "shortcut").symlink_to(tmp_path / ".git")

    assert is_git_internals_path(tmp_path / "shortcut" / "config") is True


def test_user_git_configuration_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """`git config --global` is denied on the Bash route, so the per-user
    configuration files must not stay writable on the file-edit route."""

    monkeypatch.setenv("HOME", tmp_path.as_posix())
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert is_git_internals_path(tmp_path / ".gitconfig") is True
    assert is_git_internals_path(tmp_path / ".config" / "git" / "config") is True
    assert is_git_internals_path(tmp_path / ".config" / "git" / "ignore") is True
    assert is_git_internals_path(tmp_path / ".config" / "nvim" / "init.lua") is False


def test_xdg_config_home_relocates_the_user_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("XDG_CONFIG_HOME", (tmp_path / "xdg").as_posix())

    assert is_git_internals_path(tmp_path / "xdg" / "git" / "config") is True


def test_tilde_paths_are_expanded_before_matching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("HOME", tmp_path.as_posix())

    assert is_git_internals_path(Path("~/.gitconfig")) is True


def test_build_message_names_the_protected_class():
    message = build_git_internals_edit_block_message(
        Path("/repo/.git/hooks/pre-commit")
    )
    assert message is not None
    assert "administrative area" in message


def test_build_message_allows_other_files():
    assert (
        build_git_internals_edit_block_message(Path("/repo/src/utils/config.py"))
        is None
    )


def test_build_message_allows_missing_path():
    assert build_git_internals_edit_block_message(None) is None


@pytest.mark.parametrize(
    "spelling", [".GIT", ".Git", ".gIT", ".git.", ".git ", ".\uff47\uff49\uff54"]
)
def test_alternate_spellings_of_the_administrative_entry_are_refused(spelling: str):
    """A filesystem that folds case, trims trailing dots/spaces, or normalizes
    compatibility characters resolves these to the entry itself; a
    case-sensitive volume treats them as different names, where refusing them
    is harmless over-approximation."""

    assert is_git_internals_path(Path("/repo") / spelling / "config") is True


@pytest.mark.parametrize("spelling", [".gitignore", ".github", "git", "digit"])
def test_names_that_merely_resemble_the_entry_stay_writable(spelling: str):
    assert is_git_internals_path(Path("/repo") / spelling / "x") is False


def test_alternate_case_pointer_file_rewrite_is_refused(tmp_path: Path):
    """The one-character bypass. `find_git_entry` looks up `directory/".git"`,
    so on a case-folding volume a write spelled `.GIT` lands on the very
    pointer file the ownership anchor is read from — and re-points it."""

    main = tmp_path / "main"
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    attacker = main / ".agents.worktrees" / "wt"
    attacker.mkdir(parents=True)
    pointer = attacker / ".git"
    pointer.write_text(
        f"gitdir: {(main / '.git' / 'worktrees' / 'wt').as_posix()}\n",
        encoding="utf-8",
    )

    forged = tmp_path / "forged"
    (forged / ".git" / "worktrees" / "victim").mkdir(parents=True)
    victim = forged / ".agents.worktrees" / "victim"
    victim.mkdir(parents=True)
    (victim / ".git").write_text(
        f"gitdir: {(forged / '.git' / 'worktrees' / 'victim').as_posix()}\n",
        encoding="utf-8",
    )

    command = f"git -C {victim.as_posix()} reset --hard"
    assert is_git_dangerous_command(command, cwd=attacker) is True
    assert build_git_internals_edit_block_message(attacker / ".GIT") is not None

    if _volume_is_case_insensitive(tmp_path):
        # The refusal is load-bearing here: the alternate spelling names the
        # same file, so permitting it would move the anchor for real.
        assert (attacker / ".GIT").read_text(encoding="utf-8") == pointer.read_text(
            encoding="utf-8"
        )


def test_symlink_loop_path_is_refused(tmp_path: Path):
    """A symlink loop is either unresolvable (refused fail-closed on
    interpreters whose `resolve()` raises) or resolves to the path as written
    (3.13+), which names nothing administrative and whose writes the kernel
    blocks with ELOOP anyway. The `.git`-bearing spelling is refused on both."""

    (tmp_path / "loopA").symlink_to(tmp_path / "loopB")
    (tmp_path / "loopB").symlink_to(tmp_path / "loopA")

    if _resolve_breaks_symlink_loops_silently(tmp_path):
        assert is_git_internals_path(tmp_path / "loopA" / "config") is False
    else:
        assert is_git_internals_path(tmp_path / "loopA" / "config") is True
    assert is_git_internals_path(tmp_path / "loopA" / ".git" / "config") is True


def test_embedded_null_path_is_refused():
    """`resolve()` raises `ValueError` on an embedded NUL; failing to decide is
    not evidence the path is safe."""

    assert is_git_internals_path(Path("/repo/.git/config\x00")) is True


def test_unresolvable_home_does_not_escape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """`_home_directories` resolves the home directory too, and that resolution
    raises the same way. An ordinary source file must still be allowed."""

    (tmp_path / "loopA").symlink_to(tmp_path / "loopB")
    (tmp_path / "loopB").symlink_to(tmp_path / "loopA")
    monkeypatch.setenv("HOME", (tmp_path / "loopA").as_posix())
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert is_git_internals_path(tmp_path / "src" / "utils" / "config.py") is False
    assert is_git_internals_path(tmp_path / "loopA" / ".gitconfig") is True


def test_user_configuration_alternate_spellings_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("HOME", tmp_path.as_posix())
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

    assert is_git_internals_path(tmp_path / ".GitConfig") is True
    assert is_git_internals_path(tmp_path / ".config" / "GIT" / "config") is True


def test_hook_blocks_a_path_inside_the_administrative_area():
    done = _run_hook({"tool_input": {"file_path": "/repo/.git/config"}})

    assert done.returncode == BLOCK_EXIT_CODE
    assert "administrative area" in done.stderr


def test_hook_allows_an_ordinary_path():
    done = _run_hook({"tool_input": {"file_path": "/repo/src/utils/config.py"}})

    assert done.returncode == 0
    assert done.stderr == ""


@pytest.mark.parametrize(
    ("payload", "label"),
    [
        ("{not json", "unparsable stdin"),
        ({"tool_input": 5}, "tool_input of the wrong type"),
        (
            {"tool_input": {"file_path": ["/repo/.git/config"]}},
            "path of the wrong type",
        ),
    ],
)
def test_hook_fails_closed_on_an_unexpected_exception(payload: object, label: str):
    """An exit code of 1 is a NON-blocking error: the tool proceeds. So an
    exception escaping the hook would permit the very write it was asked to
    judge."""

    done = _run_hook(payload)

    assert done.returncode == BLOCK_EXIT_CODE, f"{label}: {done.stderr}"
    assert "could not decide" in done.stderr


def _run_with_forged_record(record: Path, forged_sha: str) -> str | None:
    """Rewrite `record`'s recorded SHAs the way a file-edit tool writes a file,
    then ask the push gate to authorize a push of `forged_sha`.

    `sha_resolves` is injected as established: since the push gate also
    verifies that a RECORDED SHA names a real commit, the realistic forgery
    carries the attacker's own unverified HEAD — a commit that exists. With
    the resolution fact simulated as true, what remains under test here is
    the file-edit route to the record."""

    text = record.read_text(encoding="utf-8")
    record.write_text(text.replace("goodsha", forged_sha), encoding="utf-8")
    return build_git_danger_block_message(
        f"git push -u origin HEAD:{PROTECTED_BRANCH}",
        cwd=record.parents[3] / "worktree",
        rev_parse_head=lambda _location: forged_sha,
        sha_resolves=lambda _location, _sha: True,
    )


def test_a_written_authorization_record_authorizes_a_push_the_gate_denied(
    tmp_path: Path,
):
    """The subject of the decision writes the decision's own input. The record
    the push gate reads is an ordinary Markdown file: rewriting its recorded
    SHAs turns a denied push into an authorized one, with no git command
    involved anywhere in the forgery."""

    main_repo = tmp_path / "main-repo"
    (main_repo / ".git").mkdir(parents=True)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text(
        f"gitdir: {main_repo}/.git/worktrees/agent-1\n", encoding="utf-8"
    )

    record = main_repo / record_path_for_branch(PROTECTED_BRANCH)
    verified = "goodsha"
    write_plan_run_state(
        record,
        PlanRunState(
            status="InProgress",
            branch=PROTECTED_BRANCH,
            integration_worktree=str(worktree),
            verify_status_sha=verified,
            secret_scan_clean_sha=verified,
            pr_url="",
            terminal_outcome="",
        ),
    )

    honest = build_git_danger_block_message(
        f"git push -u origin HEAD:{PROTECTED_BRANCH}",
        cwd=worktree,
        rev_parse_head=lambda _location: "attackersha",
        sha_resolves=lambda _location, _sha: True,
    )
    assert honest is not None
    assert "verify-status SHA" in honest

    assert _run_with_forged_record(record, "attackersha") is None

    done = _run_hook({"tool_input": {"file_path": str(record)}})
    assert done.returncode == BLOCK_EXIT_CODE, done.stderr
    assert "authorization record" in done.stderr


def test_the_record_path_the_push_gate_reads_is_refused(tmp_path: Path):
    """The class is derived from the record's own owner, not restated: the path
    under test is the one `record_path_for_branch` produces."""

    assert (
        is_plan_run_record_path(tmp_path / record_path_for_branch("plan/foo")) is True
    )


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("docs/runs/plan-runs/sdd-atc-auth.md", True),
        ("docs/runs/plan-runs", True),
        ("docs/runs/plan-runs/archive/old.md", True),
        ("DOCS/RUNS/Plan-Runs/sdd-atc-auth.md", True),
        # The rest of `docs/runs/` is ordinary working state every
        # implementer writes: the vendored ledger and the group notes.
        ("docs/runs/some-plan/progress.md", False),
        ("docs/runs/some-plan/group-atc-auth-notes.md", False),
        ("docs/runs/plan-runs.md", False),
        ("docs/runs/parallel-run-state.md", False),
        ("docs/plan-runs/notes.md", False),
    ],
)
def test_plan_run_record_class_membership(relative: str, expected: bool):
    assert is_plan_run_record_path(Path("/repo") / relative) is expected


def test_plan_run_record_path_allows_missing_path():
    assert is_plan_run_record_path(None) is False


def test_symlink_into_the_record_directory_is_refused(tmp_path: Path):
    """A path whose written form names nothing protected, whose resolved form
    lands in the record directory."""

    records = tmp_path / record_path_for_branch("plan/foo").parent
    records.mkdir(parents=True)
    (tmp_path / "shortcut").symlink_to(records)

    assert is_plan_run_record_path(tmp_path / "shortcut" / "plan-foo.md") is True


def test_undecidable_record_paths_are_refused(tmp_path: Path):
    """Fail closed: being unable to establish a path's form is not evidence it
    lies outside the class. On 3.13+ a symlink loop resolves to the path as
    written, which is decidable and outside the class (the kernel blocks any
    write through the loop), so only the unresolvable spelling is pinned."""

    (tmp_path / "loopA").symlink_to(tmp_path / "loopB")
    (tmp_path / "loopB").symlink_to(tmp_path / "loopA")

    if not _resolve_breaks_symlink_loops_silently(tmp_path):
        assert is_plan_run_record_path(tmp_path / "loopA" / "x.md") is True
    assert is_plan_run_record_path(Path("/repo/x.md\x00")) is True


def test_protected_edit_message_names_the_class_it_refused():
    """`INV-1`: a denial names its specific reason, so the two classes this
    guard holds do not share one message."""

    record = build_protected_edit_block_message(
        Path("/repo/docs/runs/plan-runs/sdd-atc-auth.md")
    )
    internals = build_protected_edit_block_message(Path("/repo/.git/config"))

    assert record is not None
    assert "authorization record" in record
    assert "administrative area" not in record
    assert internals is not None
    assert "administrative area" in internals


def test_protected_edit_message_allows_ordinary_paths():
    assert build_protected_edit_block_message(Path("/repo/src/utils/config.py")) is None
    assert build_protected_edit_block_message(None) is None


def test_hook_blocks_an_authorization_record_and_says_why():
    done = _run_hook(
        {"tool_input": {"file_path": "/repo/docs/runs/plan-runs/plan-x.md"}}
    )

    assert done.returncode == BLOCK_EXIT_CODE
    assert "authorization record" in done.stderr


def test_hook_still_allows_the_ledger_beside_the_record_directory():
    """The vendored per-task ledger lives under `docs/runs/` too, and
    every implementer writes it — refusing it would stop the workflow this
    guard exists to protect."""

    done = _run_hook(
        {"tool_input": {"file_path": "/repo/docs/runs/some-plan/progress.md"}}
    )

    assert done.returncode == 0
    assert done.stderr == ""


def test_a_relative_edit_is_judged_against_the_payload_working_directory(
    tmp_path: Path,
):
    """`FIX-1`: a relative `file_path` names a file under the working directory
    the TOOL LAYER reports, not the one this hook process happens to have been
    started in. Measured on this harness: a bare filename written through the
    file-edit tool was created under the session's own directory, and the
    payload carries that directory in its `cwd` field. Both directions are
    asserted, so the verdict cannot merely happen to agree with the process."""

    records = tmp_path / record_path_for_branch("plan/foo").parent
    records.mkdir(parents=True)
    benign = tmp_path / "elsewhere"
    benign.mkdir()

    inside = _run_hook(
        {"tool_input": {"file_path": "plan-foo.md"}, "cwd": records.as_posix()},
        process_cwd=benign,
    )
    outside = _run_hook(
        {"tool_input": {"file_path": "notes.md"}, "cwd": benign.as_posix()},
        process_cwd=records,
    )

    assert inside.returncode == BLOCK_EXIT_CODE, inside.stderr
    assert "authorization record" in inside.stderr
    assert outside.returncode == 0, outside.stderr
    assert outside.stderr == ""


def test_relative_paths_are_anchored_at_the_supplied_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The process's own directory is moved into the record directory for the
    duration, so a verdict that consulted `os.getcwd()` would be visible."""

    records = tmp_path / record_path_for_branch("plan/foo").parent
    records.mkdir(parents=True)
    benign = tmp_path / "elsewhere"
    benign.mkdir()
    monkeypatch.chdir(records)

    assert is_plan_run_record_path(Path("plan-foo.md"), cwd=records) is True
    assert is_plan_run_record_path(Path("notes.md"), cwd=benign) is False
    assert is_git_internals_path(Path("config"), cwd=tmp_path / ".git") is True
    assert is_git_internals_path(Path("config.py"), cwd=benign) is False


def test_a_relative_path_with_no_usable_working_directory_is_refused():
    """Fail closed, the same posture `git_write_guard` states for every rule
    that depends on `cwd`: nothing establishes where the write would land, and
    being unable to rule a path out is not evidence it is safe. A relative
    working directory is no base either — it would send the decision straight
    back to the process."""

    assert is_plan_run_record_path(Path("plan-foo.md")) is True
    assert is_git_internals_path(Path("notes.md")) is True
    assert is_plan_run_record_path(Path("notes.md"), cwd=Path("relative/base")) is True


def _loop_at(directory: Path) -> Path:
    """A symlink loop under `directory`, whose resolution raises rather than
    resolving — the shape of a path whose form cannot be established."""

    (directory / "loopA").symlink_to(directory / "loopB")
    (directory / "loopB").symlink_to(directory / "loopA")
    return directory / "loopA"


def test_an_undecidable_path_is_refused_without_claiming_a_class(tmp_path: Path):
    """`FIX-2`: the refusal is correct, the diagnostic was not. Every
    fail-closed refusal used to be reported as an edit inside git's
    administrative area — including a path with no protected component at all —
    sending a blocked agent to debug a git problem it does not have."""

    if not _resolve_breaks_symlink_loops_silently(tmp_path):
        unrelated = build_protected_edit_block_message(_loop_at(tmp_path) / "notes.md")

        assert unrelated is not None
        assert "could not be established" in unrelated
        assert "administrative area" not in unrelated
        assert "authorization record" not in unrelated

    embedded_null = build_protected_edit_block_message(Path("/repo/notes.md\x00"))
    assert embedded_null is not None
    assert "could not be established" in embedded_null
    assert "administrative area" not in embedded_null


def test_an_undecidable_path_inside_a_protected_class_still_names_that_class(
    tmp_path: Path,
):
    """A class that decides on the path as written outranks a class that could
    not decide at all: this path is a record whatever its resolved form is."""

    records = tmp_path / record_path_for_branch("plan/foo").parent
    records.mkdir(parents=True)

    message = build_protected_edit_block_message(_loop_at(records) / "plan-foo.md")

    assert message is not None
    assert "authorization record" in message


def test_class_message_builders_stay_closed_on_an_undecidable_path(tmp_path: Path):
    """A direct consumer of one class's builder must not read None — an absent
    reason is an open gate — but must not be told the wrong class either."""

    if _resolve_breaks_symlink_loops_silently(tmp_path):
        pytest.skip("3.13+ realpath breaks symlink loops without raising")

    loop = _loop_at(tmp_path) / "notes.md"

    for message in (
        build_git_internals_edit_block_message(loop),
        build_plan_run_record_edit_block_message(loop),
    ):
        assert message is not None
        assert "could not be established" in message


def test_hook_refuses_an_undecidable_path_without_naming_a_class(tmp_path: Path):
    if _resolve_breaks_symlink_loops_silently(tmp_path):
        # 3.13+ decides the loop path (it resolves to itself), so the hook
        # allows it; an unresolvable spelling is exercised by the NUL case in
        # test_hook_fails_closed_on_an_unexpected_exception instead.
        pytest.skip("3.13+ realpath breaks symlink loops without raising")

    done = _run_hook(
        {"tool_input": {"file_path": str(_loop_at(tmp_path) / "notes.md")}}
    )

    assert done.returncode == BLOCK_EXIT_CODE, done.stderr
    assert "could not be established" in done.stderr
    assert "administrative area" not in done.stderr
