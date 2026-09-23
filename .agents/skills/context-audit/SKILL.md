---
name: context-audit
description: Full-spectrum health check of this repo's Claude Code/ZCode agent infrastructure — root AGENTS.md, .agents/rules, .agents/skills, .agents/workflows, .claude/.zcode symlink projections, settings.json, hooks. Detects drift (claims no longer true), rot (once-true, now superseded), dead-but-undeleted automation, and stack-mismatched boilerplate. Read-only until the user confirms a batch of fixes. Use whenever someone wants to audit, review, or clean up the agent/skill/workflow setup — "audit our claude setup", "is AGENTS.md up to date", "what's stale in our rules", "clean up .agents/", "check our hooks and settings" — even if they don't use the word "audit".
disable-model-invocation: true
argument-hint: "[all|rules|skills|workflows|settings|hooks|projections]"
---

# context-audit

Read-only audit of this repo's agent context infrastructure. Produces a structured report grouped by layer, then lets the user pick what to fix via `AskUserQuestion` — nothing is edited until they confirm.

**Why this exists.** This repo's agent context is unusually layered: canonical sources live in `.agents/` and are symlinked into `.claude/` (and, where a consumer uses Codex, `.codex/`); ZCode reads the `.zcode/commands` symlink; several files (`tdd-guide.md`, `security-reviewer.md`) are dispatched by *name* from `detailed-plan.md`; and a consumer project may carry a dedicated test suite (`tests/unit/test_*_projection.py`, `test_agents_inventory_sync.py`, `test_parallel_agent_workflow_policy.py`) that hard-asserts exact phrases inside specific files. That combination makes silent drift expensive: a file can look redundant in isolation but be load-bearing for a routing reference or a test. This skill exists to catch that before deleting or rewriting anything.

## Step 0 — Detect the layout

```bash
ls .claude/ .codex/ .zcode/ 2>/dev/null
ls .agents/rules/ .agents/skills/ .agents/workflows/ .agents/hooks/ .agents/scripts/ .agents/instincts/ .agents.local.toml 2>/dev/null
git ls-files .claude/agents .claude/commands .claude/rules .claude/skills .zcode/commands 2>/dev/null   # confirm symlink vs real files
```

## Step 1 — Inventory + cross-reference

Before reading file content, establish ground truth:

```bash
# Every place a workflow/skill/agent name could be referenced
rg -l "tdd-guide|security-reviewer|<name>" --type py --type md .

# What does the test suite pin down, where one exists? (these are the tripwires — read before editing anything they touch)
rg -l "\.agents/(workflows|skills|rules)/" tests/unit/

# Plugin/hook config — is it still what this project expects?
cat .claude/settings.json
```

Never delete or rewrite a file under `.agents/` without first grepping the full repo (not just `.agents/`) for its path and its bare name — a hit in `detailed-plan.md` or a `tests/unit/test_*.py` file means it's structurally wired, not just documentation.

## Step 2 — Recency + stack-fit signals

```bash
git log --since="3.months" --format="%as %s" --name-only -- .agents/ | head -60
git log --format="%as %s" -- CLAUDE.md AGENTS.md .agents/AGENTS.md | head -20
```

For every skill/workflow file, check its examples/commands against the *actual* stack — the project's real test runner, type checker, linter, and package manager (e.g. `python3 -m pytest`/`pyright`/`ruff` for Python, `npm run lint`/`tsc` for a TypeScript frontend). A file that uses `npm test`, `Jest`, `Supabase`, `Playwright`, `express-rate-limit`, or similar when the project has none of them is either misplaced boilerplate from a generic template pack, or genuinely stale and needs its examples corrected in place (not deleted, if it's structurally referenced — see Step 1).

## Step 3 — Layer checks

**Rules (`.agents/rules/`)** — one rule per file, ~10-30 lines. Path-scoped rules: does the glob still match real files? Antipattern rules: does `rg` for the antipattern still find hits? Zero hits on both = candidate to retire.

**Skills (`.agents/skills/*/SKILL.md`)** — `name`+`description` frontmatter present. Description carries real trigger phrases. Check `origin:` frontmatter — `origin: ECC` or similar marks vendored-pack content; verify it wasn't adapted (stack mismatch is the tell). Check for duplication against `.agents/rules/auto-skills.md`'s inline sections — a skill whose full content is already inline in an always-on rule provides no additional invocation surface and is a deletion candidate.

**Workflows (`.agents/workflows/*.md`)** — every file referenced from `.agents/AGENTS.md`'s agent table must exist (test-enforced, where the suite includes an inventory-sync test). Every file referenced *by name* from another workflow (e.g. `detailed-plan.md` calling out `tdd-guide`) is structurally load-bearing — fix content in place, don't delete.

**Projections (`.claude/agents`, `.claude/commands`, `.claude/skills`, `.claude/rules`, `.zcode/commands`, `.codex/*` where present)** — confirm symlinks resolve (`readlink`), and confirm any projection-validation test's expectations match what's actually on disk.

**Settings/hooks/scripts (`.claude/settings.json`, `.agents/hooks/`, `.agents/scripts/`)** — every `hooks[*].command` path must exist on disk (test-enforced by a hooks-portability test, where present — exact-match, not substring), and every hook/script invocation should run as `python3 .agents/hooks/<name>.py` / `python3 .agents/scripts/<name>.py`. `enabledPlugins`/`extraKnownMarketplaces`: are the plugins this team actually uses present, or only active via someone's personal `~/.claude/settings.json`? A plugin that's real, useful, and undocumented here is the most common miss. A `.agents.local.toml` at the repo root, when present, is the consumer's override surface for `.agents/config.toml` — it should never be edited inside a shared checkout's `.agents` tree.

**Instincts (`.agents/instincts/`)** — for each YAML, check whether its `Action` is already stated in root `AGENTS.md` or `.agents/rules/python-antipatterns.md` near-verbatim. If so, it's a duplicate lessons store, not new knowledge — flag for removal in favor of the root doc.

## Step 4 — Report

```
## context-audit Summary
<N> layers reviewed, <M> findings: <H> high / <W> med / <L> low.
<One sentence on overall health.>

## Layer: <name>
1. [high|med|low] [drift|rot|dead-automation|stack-mismatch] — <one-line>
   Evidence: <command + output that proved it>
   Proposed: <the actual fix, or "delete" with the grep proof of zero references>
```

Cap at 5 high / 8 med / 10 low per layer; state `0 high` explicitly when true. A finding without a concrete proposed fix and evidence isn't a finding — drop it.

**Severity rubric.** Apply mechanically so two runs on the same state land the same findings in the same buckets:

| Signal | Severity |
|---|---|
| A referenced path (hook command, symlink target, workflow file dispatched by name, e.g. from `detailed-plan.md`) does not exist on disk | high |
| A `tests/unit/test_*.py` tripwire (Step 1) asserts a path or exact phrase that no longer matches the file's actual content | high |
| A rule's `rg` pattern or path glob matches zero files, with no replacement rule covering the same risk | med |
| An example/command in a skill or workflow uses a stack the repo doesn't have (`npm test`, `Jest`, `Supabase`, `Playwright`, etc.) | med |
| Skill content is duplicated verbatim in `auto-skills.md` with no added invocation surface | med |
| An `.agents/instincts/` entry restates root `AGENTS.md`/`python-antipatterns.md` near-verbatim | med |
| Wording/phrasing drift, a stale-but-harmless example, or a count off by one item with no functional impact | low |

## Step 5 — Let the user pick

Use `AskUserQuestion` with `multiSelect: true`. Map each finding/initiative to an option (`#N [severity] one-liner`). Don't apply anything yet.

## Step 6 — Apply

Apply only what was selected. For any deletion of a file with references found in Step 1, re-run the grep after the edit to confirm zero stragglers — the antipattern this skill exists to prevent is "fixed one instance, left another" (see `.agents/rules/python-antipatterns.md` Rule 28). If test files assert on the deleted/changed content, update them in the same pass — never leave the test suite red.

## Constraints

- Read-only through Step 4. No edits before the user's Step 5 selection.
- Never assume a file is dead because it looks generic — grep the whole repo and the test suite first (Step 1 is mandatory, not optional).
- Report only layers that exist in this repo; don't invent a `.claude-plugin/` section, this isn't a plugin repo.
