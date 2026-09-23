# startuper-workflows

Standalone, multi-host agentic development workflows: a complete planning →
parallel subagent-driven execution → review → PR system for coding agents,
installable into any repository.

Works with **Claude Code** and **ZCode**. PRs land via the GitHub `gh` CLI.

> Full documentation is being written — see the workflow catalog in
> [.agents/AGENTS.md](.agents/AGENTS.md) in the meantime.

## What's inside

- **Slash commands** (`.agents/workflows/`): `/architect`, `/detailed-plan`,
  `/deliberation`, `/root-cause-analysis`, `/extract-issues`,
  `/commit-message`, `/chat`, `/explain`, `/just-answer`
- **Skills** (`.agents/skills/`): `parallel-subagent-driven-development`,
  `detailed-plan`, `task-spec`, `code-review-fix-loop`, `technical-spike`,
  `critical-thinking`, `progress-report`, and more
- **Specialists** (`.agents/specialists/`): read-only reviewer/scout agents
- **Rules** (`.agents/rules/`): ambient guardrails auto-loaded each session
- **Hooks** (`hooks/`): Python guard hooks (git-mutation blocking, context
  budget guards, memory-consent enforcement) wired via `.claude/settings.json`
- **Scripts** (`scripts/`): worktree acquisition with per-run capacity caps,
  plan grouping, run-state tooling

## Status

Under construction — first public release in progress.

## License

[MIT](LICENSE)
