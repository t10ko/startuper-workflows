# Rules

## Structure

Rules live as top-level Markdown files:

```text
rules/
├── agent-worktrees.md
├── architectural-reliability.md
├── auto-skills.md
├── block-git-mutations.md
├── clean-typing.md
├── deliver-closed-domains-to-producers.md
├── execution-continuity.md
├── findings-go-in-decision-notes.md
├── github-pr-api.md
├── memory-consent.md
├── model-assignment.md
├── no-hardcoded-pattern-names-in-prompts.md
├── no-overfitted-fixes.md
├── no-real-api-calls-in-tests.md
├── no-unjustified-fallbacks.md
├── no-unjustified-killswitches.md
├── provider-schema-transport-fidelity.md
├── python-antipatterns.md
├── repomix-protocol.md
├── response-contract.md
├── root-cause-before-guardrails.md
├── single-source-of-truth.md
└── sizing-agent-work.md
```

- `agent-worktrees.md` is the auto-loaded, agent-facing statement of the agent-owned worktree rule: `.agents.worktrees/<name>` is the one root where `git worktree add` succeeds and where a working-tree-scoped deny-list drops away; force-removing a worktree and force-deleting an `sdd/`/`plan/` branch are separately gated by target, not by standing inside one; shared-repo-state commands (`config`, `remote`, `gc --prune`, `reflog expire`, and `send-pack`) stay blocked everywhere, while `push` keeps its own separate, unchanged canonical-form authorization; and path-based ownership is a guardrail, not a security boundary against arbitrary Bash.
- `architectural-reliability.md` enforces simplicity and design-time fault avoidance: prefer the simplest design, reuse established patterns, and don't abstract around hypothetical variation.
- `auto-skills.md` holds always-on behavioral skills.
- `block-git-mutations.md` mirrors the git-mutation-blocking hook's deny-list (blocks a specific set of destructive patterns; most git commands are allowed) for passive rule systems.
- `clean-typing.md` enforces repo typing rigor from code review policy.
- `deliver-closed-domains-to-producers.md` requires a field whose legal values form a closed set to deliver that set to the model producing it, by the route matching the set's lifetime, and to fail loud rather than let a value be invented or a violation swallowed.
- `execution-continuity.md` states when an agent keeps going without checking in: once a plan is approved its pace is approved too, and only a real blocker, a decision the plan never settled, or completion justifies stopping mid-plan.
- `findings-go-in-decision-notes.md` puts every noticed-but-unfixed problem in a decision note under `docs/decision-notes/` and nowhere else -- never a code comment, a plan, a run-state file or a commit message; a comment reaching only whoever opens that file is invisible to anyone asking what is still open, and dies with the file.
- `github-pr-api.md` centralizes how the automated branch/PR workflow talks to GitHub through the `gh` CLI via `agentic_workflows.github_client` — the four allowed operations, `gh auth login` auth, PR `state` semantics (`OPEN`/`MERGED`/`CLOSED`), the single canonical push form, and what the workflow must never do (merge/close/approve a PR).
- `memory-consent.md` is the canonical memory-consent protocol: no agent writes a memory record without explicit in-session user consent, reads are never gated, and untracked per-machine memory stores (`~/.claude/**/memory/`, `.remember/`) must never be written to.
- `model-assignment.md` is the only place that decides which model a dispatched subagent runs on: the cheapest tier never, a standard-capability model always for any role that changes project source, and a deeper model only for an investigation role whose dispatch states a reason; no plan, tier, or escalation may raise an implementer. Each harness maps tiers onto its own model lineup.
- `no-hardcoded-pattern-names-in-prompts.md` bans naming a specific structural pattern (e.g. "a heading", "a table") in prompt/instruction text as if the name were the fix; teach the general reusable-concept recognition instead.
- `no-overfitted-fixes.md` requires a fix for a confirmed, generally-scoped problem to be designed
  at that same general level (e.g., a judgment-based mechanism) rather than narrowed to match only
  the current test data's specific formatting or convention.
- `no-real-api-calls-in-tests.md` bans real network/provider calls in tests, including via un-awaited background threads/tasks that can escape mocks and the global network guard.
- `no-unjustified-fallbacks.md` bans a fallback, default, or backward-compatibility path without a concrete, stated reason: the condition that reaches it, why continuing beats failing, and confirmation the fallback path itself produces a correct (not merely non-crashing) result.
- `no-unjustified-killswitches.md` forbids speculative feature flags, config killswitches, and dead fallback toggles without a concrete, stated operational deployment need.
- `provider-schema-transport-fidelity.md` requires verifying a schema construct survives transport to the configured provider and model before relying on it to enforce a rule on model output.
- `python-antipatterns.md` catalogs Python typing/lint antipatterns (e.g. `Any`, `cast()`, loose `dict`) and the project-preferred fix for each.
- `repomix-protocol.md` documents repomix usage and optimization protocols.
- `response-contract.md` is the single source of truth for how every message to the user is formatted and shaped, combining behavioral constraints, visual delimiters, ADHD cognitive ergonomics, dynamic visual modulation, and the full Markdown device palette. It is re-injected on every turn by a `UserPromptSubmit` hook in addition to auto-loading, because only per-turn injection survives a long session without decaying. `tests/unit/test_response_contract.py` pins a 20-line ceiling and asserts the deleted companion files stay deleted.
- `root-cause-before-guardrails.md` requires finding and fixing the root behavioral cause of a bug before proposing a guardrail/validation check as "the fix"; a guardrail is only a safety net added afterward.
- `single-source-of-truth.md` gives a value with one meaning exactly one owner: two writable stores of it is a defect when written, not once they diverge; duplication is collapsed, not synchronized.
- `sizing-agent-work.md` states the four rules that decide what agent work costs, all derived from 53,622 measured turns in which 98.29% of every billed token was re-read context: a group's thinking tier follows its own work kind rather than the plan's profile, verbatim file relocation is a shell command rather than a model retyping text, tasks are cut along file ownership — a file several requirements need gets one owning task the rest consume, and two pieces fuse only when neither can be shown to work without the other — and a dispatch round trip is capped to a brief sent by path plus a five-line report.

## Claude Code projection

Every file above is read directly by ZCode. Claude Code
projects this directory into `.claude/rules/` as one real symlink per file
(the same per-file symlink pattern `.claude/agents` already uses) instead of
a single directory symlink, so it can control what auto-loads rather than
taking everything here. Two independent mechanisms do that.

**Exclusion — no symlink at all.** Which files are excluded is defined in
exactly one place, and it is not this file: the `CLAUDE_RULES_EXCLUDED`
constant in `tests/unit/test_claude_projection.py`. Read the set there.
This section deliberately does not restate it — a hand-typed second copy
of a value is a defect the moment it is written
(`single-source-of-truth.md`), and Markdown prose cannot be derived from
a Python constant, so a copy here could only ever be kept in step by
hand. What belongs here is why a file earns exclusion at all: a
prohibition that a live `PreToolUse` hook under `.agents/hooks/` enforces
whether or not any agent ever reads the rule is already in force without
an ambient copy, and a table of contents — which is what this file is —
is not a rule for an agent to follow.

**Deferral — projected, but carrying a `paths:` frontmatter key.** Claude
Code loads such a file only once it reads a file matching one of the globs,
instead of at session start. A glob ending in `/**` covers that directory
and everything under it; a `paths:` list that is empty, or entirely `**`,
disables deferral and the file loads unconditionally. Which rules are scoped
this way, and behind which globs, is defined in exactly one place, and it is
not this file: the `EXPECTED_DEFERRED_RULE_GLOBS` constant in
`tests/unit/test_claude_rules_payload_budget.py`. Read the set there — this
section restates neither the names nor the globs, for the same reason the
paragraph above restates no exclusion set, and a prose list of seven where
the constant held eight is exactly how that goes wrong. What belongs here is
when deferral is safe at all: a rule that can only be broken by editing a
file its own globs already cover has been read by everyone in a position to
break it, while a rule about where to *put* something an agent noticed, or
about a permission it has to know it holds, reaches nobody if it waits for a
matching file to be opened.

Two costs of deferral, stated here rather than left to be rediscovered:

- A `paths:` glob must actually cover the code its rule governs. A glob
  matching nothing defers that rule **forever** — strictly worse than either
  excluding the file or leaving it always-on, and completely silent.
- Scoping something `**/*.py` barely defers it here. Every rule carrying that
  glob loads for essentially any agent that opens a Python file — three of
  them as of 2026-08-27, ~24.2 KB together, deferred in the byte budget but
  not in practice for Python work. The saving is real only for agents that
  never touch a `.py` file.

Both mechanisms are pinned by tests, because both fail silently otherwise:
the exclusion owner named above, besides holding that set, asserts
`.claude/rules/` holds exactly one relative symlink per non-excluded rule
file, so a symlink cannot quietly appear or vanish; the deferral owner named
above caps the always-on byte total and asserts every declared `paths:`
pattern still reaches a real file.
`tests/unit/test_agents_rules_readme_inventory.py` checks only that those two
pointers still resolve — that each module exists, still defines the constant
named, is named here exactly once and in the same paragraph as that constant,
and that no member of the set being handed over is named in that paragraph.
So a mention in *another* paragraph cannot keep a repointed sentence green,
and a re-added enumeration beside a pointer fails. A decoy inside the same
paragraph still passes — a repointed sentence keeping the old path as a
parenthetical — and that limit is recorded in the test rather than closed,
because closing it means parsing sentences. No test reads a membership claim
out of this prose, because this prose no longer makes one.

## Rules vs Skills

- **Rules** define standards, conventions, and checklists that apply broadly (e.g., "80% test coverage", "no hardcoded secrets").
- **Skills** (`skills/` directory) provide deep, actionable reference material for specific tasks (e.g., `python-patterns`, `golang-testing`).

Rules tell agent _what_ to do; skills tell agent _how_ to do it.
