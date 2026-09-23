"""GitHub pull-request operations for the landing workflow, via the `gh` CLI.

The one seam between the landing workflow and the forge. Everything here
shells out to `gh` (authenticated ahead of time with `gh auth login`); no
tokens are read, stored, or logged by this module. Never merges, declines,
closes, or approves: the pull-request review is the run's human checkpoint,
and this client's job ends at opening and keeping the PR's description
current.

Every PR-facing call secret-scans its text fields first (`scan_text_for_secrets`)
and refuses the call — naming the finding's location, never the matched value —
so a leaked credential in a generated title or description never reaches the
remote.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from agentic_workflows.secret_scan import scan_text_for_secrets


class GitHubClientError(RuntimeError):
    """A `gh` invocation failed, or returned an undecidable answer."""


class GitHubSecretScanError(RuntimeError):
    """A PR text field contained a credential-shaped value; the call was
    refused. The message names fields and match locations, never values."""


@dataclass(frozen=True)
class PullRequestInfo:
    """The slice of a PR the landing workflow reads or writes."""

    number: int
    state: str
    url: str
    title: str


def _run_gh(args: list[str], *, repo: str | None) -> str:
    command = ["gh"]
    if repo is not None:
        command += ["-R", repo]
    command += args
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as error:
        raise GitHubClientError(
            "gh CLI not found in PATH; install it (https://cli.github.com) "
            "and authenticate with `gh auth login` before landing a run."
        ) from error
    except subprocess.CalledProcessError as error:
        raise GitHubClientError(
            f"`gh {' '.join(args[:2])}...` failed: "
            f"{error.stderr.strip() or error}"
        ) from error
    return result.stdout


def _refuse_if_secrets_found(field_name: str, text: str) -> None:
    matches = scan_text_for_secrets(text)
    if matches:
        locations = ", ".join(f"{m.secret_type} on line {m.line_number}" for m in matches)
        raise GitHubSecretScanError(
            f"refusing the PR call: {field_name} contains credential-shaped "
            f"value(s) ({locations}). Remove or redact them; the values "
            "themselves are deliberately not repeated here."
        )


def find_open_pull_request(
    branch: str,
    *,
    repo: str | None = None,
    base: str = "main",
) -> PullRequestInfo | None:
    """The open PR whose head is `branch`, or None when none exists."""
    out = _run_gh(
        [
            "pr",
            "list",
            "--head",
            branch,
            "--base",
            base,
            "--state",
            "open",
            "--json",
            "number,state,url,title",
        ],
        repo=repo,
    )
    try:
        payload = json.loads(out)
    except json.JSONDecodeError as error:
        raise GitHubClientError(f"undecidable `gh pr list` output: {error}") from error
    if not isinstance(payload, list) or not payload:
        return None
    entry = payload[0]
    return PullRequestInfo(
        number=int(entry["number"]),
        state=str(entry["state"]),
        url=str(entry["url"]),
        title=str(entry.get("title", "")),
    )


def create_pull_request(
    *,
    title: str,
    body: str,
    base: str = "main",
    head: str,
    repo: str | None = None,
) -> PullRequestInfo:
    """Open one PR; refuses before any network call if title or body scans dirty."""
    _refuse_if_secrets_found("PR title", title)
    _refuse_if_secrets_found("PR body", body)
    out = _run_gh(
        [
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--base",
            base,
            "--head",
            head,
        ],
        repo=repo,
    )
    url = out.strip().splitlines()[-1].strip() if out.strip() else ""
    created = find_open_pull_request(head, repo=repo, base=base)
    if created is None:
        raise GitHubClientError(
            f"`gh pr create` returned {url!r} but no open PR is visible for "
            f"head branch {head!r}; refusing to report an unverifiable PR."
        )
    return created


def get_pull_request_state(pr_id: int, *, repo: str | None = None) -> str:
    """The PR's state: exactly one of `OPEN`, `MERGED`, `CLOSED`.

    The landing workflow requires `OPEN` before any continuation push; any
    other value (or an unrecognized one) halts the run rather than pushing.
    """
    out = _run_gh(
        ["pr", "view", str(pr_id), "--json", "state"],
        repo=repo,
    )
    try:
        payload = json.loads(out)
    except json.JSONDecodeError as error:
        raise GitHubClientError(f"undecidable `gh pr view` output: {error}") from error
    state = payload.get("state") if isinstance(payload, dict) else None
    if not isinstance(state, str) or not state:
        raise GitHubClientError(
            f"`gh pr view` returned no usable state for PR {pr_id}: {payload!r}"
        )
    return state


def update_pull_request_description(
    pr_id: int,
    body: str,
    *,
    repo: str | None = None,
) -> None:
    """Replace the PR body; refuses before any network call if it scans dirty."""
    _refuse_if_secrets_found("PR body", body)
    _run_gh(["pr", "edit", str(pr_id), "--body", body], repo=repo)
