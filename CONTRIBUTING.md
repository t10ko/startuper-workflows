# Contributing

## Layout contract

```
.agents/                  canonical, host-agnostic tree — the install unit
  AGENTS.md               orchestrator doc (root AGENTS.md/CLAUDE.md symlink here)
  workflows/              slash commands (markdown)
  skills/<name>/          SKILL.md + references/ + agents/ (+ design-notes.md)
  specialists/            read-only reviewer/scout agents
  rules/                  ambient rules, auto-loaded via .claude/rules projection
  hooks/                  Claude Code guard-hook entry points (python3, stdlib only)
  scripts/                orchestration scripts (python3, stdlib only)
  config.toml             default tunables (consumers override via .agents.local.toml)
agentic_workflows/        the stdlib-only Python runtime (repo-root package)
tests/                    pytest suite; `make verify` = ruff + pytest
install.sh / uninstall.sh consumer install tooling
.claude/ .zcode/          projections of .agents (symlinks), committed
```

Rules that keep this maintainable:

1. **`.agents/` is the single source of truth.** Never edit `.claude/rules/…`
   or `.claude/agents/…` content directly — they're symlinks.
2. **Runtime stays stdlib-only.** `agentic_workflows/`, `.agents/hooks/`, and
   `.agents/scripts/` must import the standard library (3.12+) and nothing
   else. A CI check and the test suite enforce this. Third-party tools
   (`rg`, `git`, `gh`, optional `jscpd` via `npx`) are *external commands*,
   not Python imports.
3. **Prose and tests pin each other.** `tests/unit/test_skill_*` and the
   projection tests assert exact phrases and file sets in `.agents/**.md`.
   If you reword a workflow, expect to update its pinning test in the same
   change — that's the point: the tests keep the degradation notes and
   safety wording from drifting.
4. **Skill frontmatter `description:` ≤ 1024 chars** — ZCode silently drops
   longer descriptions (pinned by `test_skill_frontmatter_portability.py`).
5. **Fail-closed vs fail-open is per-guard, deliberate, and documented in the
   hook's docstring.** Safety guards (git internals, protected paths) refuse
   what they cannot decide; cost guards (file dumps) pass what they cannot
   decide. Don't flip one without updating its tests and settings
   description.

## Adding a workflow or skill

1. Markdown goes in `.agents/workflows/` (slash command) or
   `.agents/skills/<name>/SKILL.md` (skill). Frontmatter: `name:` +
   `description:` (the description is the trigger — make it precise).
2. If the skill dispatches its own private subagents, put them in
   `.agents/skills/<name>/agents/` — `install.sh` projects them as
   `<skill>-<agent>` into `.claude/agents/` automatically.
3. If it references scripts, they live in `.agents/scripts/` and must be
   stdlib-only with the same self-bootstrap header the other scripts carry.
4. Add/extend a test pinning the contract you just created, run
   `make verify`, and re-run `install.sh` in one consumer repo to see the
   projection pick it up.

## Design notes worth reading before changing the engine

`parallel-subagent-driven-development` and `code-review-fix-loop` carry
`design-notes.md` files recording the measured failures that shaped their
current rules (the proportionality-shaped failures, the iteration-cap
history, the quota-exhaustion incident, the sequential-fix cost). A change
that reopens one of those failure modes needs to say why it won't recur.
