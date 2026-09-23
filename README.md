# startuper-workflows

Standalone, multi-host agentic development workflows: a complete
**plan → parallel subagent-driven execution → review → pull request** system
for coding agents, installable into any repository.

Works with **Claude Code** and **ZCode**. Pull requests land via the GitHub
`gh` CLI. The Python runtime is **standard-library only** — no venv, no
dependency install — so it runs in repos of any language.

Extracted and generalized from a production system that has run hundreds of
real development cycles (TDD planning, multi-worktree parallel execution,
review-fix loops, guarded pushes).

---

## Why

Coding agents are reliable at the scale of one task and unreliable at the
scale of a feature. This system is the missing orchestration layer:

- **Plans before code** — every executable change starts as a
  repository-grounded plan with an explicit task decomposition, grouping
  analysis (what can run in parallel), and a test admission gate.
- **Worktrees, not vibes** — every unit of work runs in its own git
  worktree off the main checkout, leased through a capacity-capped allocator
  with durability invariants (uncommitted work is never dropped).
- **Subagents, not context soup** — implementers are fresh, small,
  role-briefed subagents; the orchestrating session never grows a 700k-token
  context doing the work itself.
- **Review is a loop with a cap** — an adversarial multi-dimension review
  runs on the combined diff; findings are fixed in file-disjoint parallel
  batches; the iteration count is *mechanically enforced* by a hook, not
  asked nicely.
- **The push is the ceremony** — one canonical push form, a secret scan on
  the diff, a verified-SHA record, and the pull request as the human
  checkpoint. Agents never merge.

## What's inside

| Layer | Location | Contents |
|---|---|---|
| Slash commands | `.agents/workflows/` | `architect`, `detailed-plan`, `deliberation`, `root-cause-analysis`, `extract-issues`, `commit-message`, `chat`, `explain`, `just-answer` |
| Skills | `.agents/skills/` | `parallel-subagent-driven-development` (the execution engine), `detailed-plan`, `task-spec`, `code-review-fix-loop`, `technical-spike`, `critical-thinking`, `progress-report`, `retro`, `strategic-compact`, `memory`, `context-audit`, `continuous-learning-v2`, `claudish-usage` |
| Specialist agents | `.agents/specialists/` | Read-only reviewers and scouts: `code-reviewer`, `security-reviewer`, `silent-failure-hunter`, `py-antipattern-specialist`, `sdd-implementer`, `sdd-reviewer`, … |
| Ambient rules | `.agents/rules/` | Guardrails auto-loaded each session (worktree lifecycle, memory consent, model-tier assignment, response contract, …) |
| Guard hooks | `.agents/hooks/` | Python guards: dangerous-git blocking, ripgrep enforcement, context-budget caps, protected-path writes, memory-consent, review-loop iteration cap |
| Orchestration scripts | `.agents/scripts/` | `worktree_acquire.py` (per-run capped worktree allocator), `parallel_plan_grouping.py`, `sdd_workspace.py`, `task_brief.py`, `review_package.py`, secret/antipattern/duplication scanners |
| Python runtime | `agentic_workflows/` | The vendored, stdlib-only modules everything above calls (guards, ledgers, lease authority, `gh`-based PR client, secret scanner) |
| Tests | `tests/` | Unit tests for the runtime, the hooks, the install tooling, and the skill/projection contracts |

## Install

Prerequisites: `git`, Python 3.12+, `rg` (ripgrep). For PR landing: the
GitHub `gh` CLI, authenticated once with `gh auth login`.

```bash
git clone git@github.com:t10ko/startuper-workflows.git ~/startuper-workflows
cd your-project
~/startuper-workflows/install.sh
```

`install.sh` (idempotent; re-run any time):

1. Symlinks `.agents/` into your repo (updates propagate on `git pull` of
   the workflows repo; use `--copy` to vendor instead).
2. Projects the slash commands, skills, rules, and agents into
   `.claude/` and `.zcode/`.
3. Merges the guard-hook wiring into your `.claude/settings.json`
   (backs up the previous file; preserves your own hooks; re-running never
   duplicates).
4. Writes `.agents.local.toml` — machine-local config overrides.

`uninstall.sh` reverses everything, leaving your own settings intact.

### Consumer-local configuration

`.agents.local.toml` (never committed; lives outside the symlinked tree so
overrides can't leak between repos):

```toml
[worktrees]
max_concurrent = 5        # per-run worktree + in-flight agent cap

[project]
verify_cmd = "make verify"  # your project's verification command (must be
                            # safe to run concurrently in separate worktrees)

[spike]
fixture = "path/to/fixture"  # only if you use technical-spike
```

## Quickstart

In Claude Code or ZCode, inside an installed repo:

```
/detailed-plan fix the flaky checkout test in payments
```

produces `docs/plans/<slug>.md` — a grouped, TDD-shaped execution plan — and
hands you the command to run it:

```
/parallel-subagent-driven-development docs/plans/<slug>.md --dont-stop --dont-ask --dont-defer
```

which creates the run branch and worktrees, dispatches a fresh implementer
subagent per task, reviews and lands each group in dependency order, runs
one integration review-fix loop plus your verify command, scans the diff for
secrets, pushes with the single canonical form, and opens a GitHub pull
request — the PR review is your human checkpoint. Worktrees are released
automatically as the run completes.

Other entries: `/architect` (proposal/conformance architecture passes),
`/task-spec` (turn a vague ticket into a grounded spec),
`/root-cause-analysis` (evidence-first investigation), `/deliberation`
(decision notes), `/extract-issues` (log mining), `/commit-message`.

## Host compatibility

| Capability | Claude Code | ZCode |
|---|---|---|
| Slash commands, skills, rules | ✅ | ✅ (commands + skills; rules read via AGENTS.md) |
| Typed specialist dispatch | ✅ native subagents | ✅ via role-file-briefed general-purpose agents (zcode-compat substitutions) |
| Guard hooks (PreToolUse, …) | ✅ enforced | ❌ prose-only (recorded degradation) |
| Background dispatch + wake lifecycle | — | ✅ |
| PR landing | ✅ via `gh` | ✅ via `gh` |

The design is deliberately multi-host with **explicit degradation notes**:
capabilities a harness lacks are recorded as accepted losses in
`references/zcode-compat.md`, never silently assumed away.

## Architecture

```
        slash command (/detailed-plan)          ── planning, evidence-gated
                      │
              approved plan (docs/plans/)
                      │
   /parallel-subagent-driven-development        ── the execution engine
                      │
     ┌───────────┬─────────────┬───────────┐
     │ group wt 1 │ group wt 2 │    ...    │   ≤ N worktrees, per-run cap
     │ implement→ │ implement→ │           │   one fresh subagent per task
     │  review    │  review    │           │   review per group pass
     └─────┬─────┴─────┬──────┴─────┬─────┘
        rolling dependency-order merge     (integration worktree)
                      │
      code-review-fix-loop (capped)  +  <verify-cmd> + secret scan
                      │
        git push -u origin HEAD:<branch>  →  gh pr create
                      │
            pull-request review = the human checkpoint
```

The `.agents/` tree is canonical; `.claude/` and `.zcode/` are projections
(symlinks) so one source of truth serves every harness. Python entry points
self-locate the runtime through symlink resolution, so the same files serve
this repo (self-hosted) and any consumer repo.

## Safety posture

- **Agents never merge PRs.** The `gh` client cannot merge/close/decline;
  the PR review is deliberately the human checkpoint.
- **One push form.** `git push -u origin HEAD:<branch>`, verified-SHA gated,
  secret-scanned, and enforced by the git-write guard hook.
- **Fail-closed where it's safety, fail-open where it's cost.** Protected-path
  and git-mutation guards refuse when they cannot decide; context-budget
  guards would rather pass a wasted command than burn a turn.
- **Destructive worktree actions are durability-gated** — uncommitted work
  is committed first, and a HEAD commit no branch holds blocks removal.
- **Memory writes require consent**; secrets are never echoed by guards.

## Development

```bash
make verify   # ruff + pytest (this repo's own checks)
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the layout contract, how the
projections and tests pin each other, and how to add a workflow.

## License

[MIT](LICENSE)
