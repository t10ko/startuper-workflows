---
trigger: glob
globs: "agentic_workflows/github_client.py,agentic_workflows/secret_scan.py,.agents/skills/parallel-subagent-driven-development/**"
paths:
  - "agentic_workflows/github_client.py"
  - "agentic_workflows/secret_scan.py"
  - ".agents/skills/parallel-subagent-driven-development/**"
---

# GitHub Pull Requests via the `gh` CLI (PR Workflow Contract)

This is the single centralized reference for how this project's automated
branch/PR workflow talks to GitHub. Nothing else in this repo should restate
this contract — link back here instead of copying these details into another
prompt, script, or doc.

## The one seam

All pull-request operations go through `agentic_workflows.github_client`,
which shells out to the `gh` CLI. It exposes exactly four operations:

| Purpose | Function |
| --- | --- |
| Find the open PR for a branch (idempotency check before creating) | `find_open_pull_request(branch)` |
| Open a PR | `create_pull_request(title, body, base, head)` |
| Read a PR's state | `get_pull_request_state(pr_id)` |
| Replace a PR's description | `update_pull_request_description(pr_id, body)` |

Never shell out to `gh` (or any other forge client) directly from a workflow,
prompt, or script: the client is the only place `gh` invocation, argument
shaping, and output parsing live.

## Auth

`gh auth login`, run once by the human ahead of time. The client reads no
token from the environment or from config, stores none, and logs none — do
not add a token mechanism, and never put a credential in a PR title or
description.

## The `state` field

A pull request's `state` is **exactly one of three values**:

- `OPEN`
- `MERGED`
- `CLOSED`

Only `OPEN` means "still open, safe to push more commits to." The landing
workflow requires `OPEN` before any continuation push; **any other value —
`MERGED`, `CLOSED`, or any unrecognized value a future forge returns — halts
the run**, fail-closed. Never write logic that treats "not `MERGED`" as
equivalent to "open"; check for the literal string `"OPEN"` and treat
everything else, known or unknown, as not-open.

## What this workflow must never do

The client never merges, closes, declines, or approves a pull request — its
function set above ends at opening a PR, reading its state, and keeping its
description current. The pull-request review is the run's human checkpoint,
made in the forge's own UI; adding any operation that completes, rejects, or
blesses a PR is a violation of this contract, not an extension of it.

Correspondingly, the single canonical push form is
`git push -u origin HEAD:<branch>`, and it is the **only** push an agent may
issue — the git-write guard denies every other shape and authorizes this one
only for a branch owned by a still-running run whose pushed commit matches
the round's verified SHAs (see `.agents/rules/block-git-mutations.md`'s push
section).

## Secret hygiene

Before this workflow sends a PR title/description to GitHub (on create *or*
on update), the client scans it for credential-shaped values via
`agentic_workflows.secret_scan.scan_text_for_secrets` and refuses the call,
naming the match's location but never the matched value. Keep every
PR-facing text field behind that scan.
