"""The `gh`-shelling PR client, with the subprocess seam patched out.

Every PR-facing call must secret-scan its text fields BEFORE it touches the
network, and every call must build the expected `gh` argv. `subprocess.run`
in `agentic_workflows.github_client` is monkeypatched with a recorder, so
"refuses before any subprocess call" is asserted by call count, not by
trusting the mock.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

import agentic_workflows.github_client as github_client
from agentic_workflows.github_client import (
    GitHubSecretScanError,
    PullRequestInfo,
    create_pull_request,
    find_open_pull_request,
    get_pull_request_state,
    update_pull_request_description,
)

# AWS's own documented example key and a synthetic PEM banner: fake values
# with the exact shapes the scanner matches.
SECRET_TITLE = "feat: add key AKIAIOSFODNN7EXAMPLE"
SECRET_BODY = "config:\n-----BEGIN RSA PRIVATE KEY-----\nbody"


@dataclass
class _FakeResult:
    stdout: str


class _RecordingGh:
    """A subprocess.run stand-in that records argv and replays canned stdout."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], **_kwargs: Any) -> _FakeResult:
        self.calls.append(args)
        return _FakeResult(stdout=self.responses.pop(0))


def test_find_open_pull_request_parses_the_gh_pr_list_payload():
    payload = [
        {
            "number": 7,
            "state": "OPEN",
            "url": "https://github.com/example/repo/pull/7",
            "title": "plan/foo: land it",
        }
    ]
    gh = _RecordingGh([json.dumps(payload)])

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(github_client.subprocess, "run", gh)
        found = find_open_pull_request("plan/foo", repo="example/repo")

    assert found == PullRequestInfo(
        number=7,
        state="OPEN",
        url="https://github.com/example/repo/pull/7",
        title="plan/foo: land it",
    )
    assert gh.calls == [
        [
            "gh",
            "-R",
            "example/repo",
            "pr",
            "list",
            "--head",
            "plan/foo",
            "--base",
            "main",
            "--state",
            "open",
            "--json",
            "number,state,url,title",
        ]
    ]


def test_find_open_pull_request_returns_none_when_no_pr_exists():
    gh = _RecordingGh(["[]"])

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(github_client.subprocess, "run", gh)
        found = find_open_pull_request("plan/foo")

    assert found is None
    assert gh.calls[0][0] == "gh"  # no `-R` when no repo was given
    assert "-R" not in gh.calls[0]


def test_create_pull_request_builds_the_expected_gh_argv():
    created_payload = [
        {
            "number": 9,
            "state": "OPEN",
            "url": "https://github.com/example/repo/pull/9",
            "title": "plan/foo",
        }
    ]
    gh = _RecordingGh(["https://github.com/example/repo/pull/9\n", json.dumps(created_payload)])

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(github_client.subprocess, "run", gh)
        pr = create_pull_request(
            title="plan/foo",
            body="## Summary\n- done",
            head="plan/foo",
            repo="example/repo",
        )

    assert pr.number == 9
    create_call = gh.calls[0]
    assert create_call[:4] == ["gh", "-R", "example/repo", "pr"]
    assert "--title" in create_call
    assert create_call[create_call.index("--title") + 1] == "plan/foo"
    assert create_call[create_call.index("--body") + 1] == "## Summary\n- done"
    assert create_call[create_call.index("--base") + 1] == "main"
    assert create_call[create_call.index("--head") + 1] == "plan/foo"


@pytest.mark.parametrize("secret", [SECRET_TITLE, SECRET_BODY])
def test_create_pull_request_refuses_a_secret_laden_field_before_any_call(secret: str):
    gh = _RecordingGh([])

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(github_client.subprocess, "run", gh)
        with pytest.raises(GitHubSecretScanError):
            create_pull_request(
                title="clean title",
                body=secret,
                head="plan/foo",
            )

    assert gh.calls == [], "the refusal must happen before any gh invocation"


def test_create_pull_request_refusal_names_the_field_but_never_the_value():
    gh = _RecordingGh([])

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(github_client.subprocess, "run", gh)
        with pytest.raises(GitHubSecretScanError) as exc_info:
            create_pull_request(
                title=SECRET_TITLE,
                body="clean",
                head="plan/foo",
            )

    message = str(exc_info.value)
    assert "PR title" in message
    assert "AKIAIOSFODNN7EXAMPLE" not in message
    assert "line 1" in message


@pytest.mark.parametrize("state", ["OPEN", "MERGED", "CLOSED"])
def test_get_pull_request_state_returns_the_state_verbatim(state: str):
    gh = _RecordingGh([json.dumps({"state": state})])

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(github_client.subprocess, "run", gh)
        result = get_pull_request_state(9, repo="example/repo")

    assert result == state
    assert gh.calls == [["gh", "-R", "example/repo", "pr", "view", "9", "--json", "state"]]


def test_update_pull_request_description_refuses_a_secret_laden_body():
    gh = _RecordingGh([])

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(github_client.subprocess, "run", gh)
        with pytest.raises(GitHubSecretScanError):
            update_pull_request_description(9, SECRET_BODY, repo="example/repo")

    assert gh.calls == []
