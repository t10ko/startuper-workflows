# Agentic Workflow System

This repo keeps canonical agent/command prompt sources in `.agents/`: commands
in `.agents/workflows/`, specialist subagents in `.agents/specialists/`, and
skill-private prompts inside each skill's own `.agents/skills/<skill>/`
folder. Claude Code reads the projected files in `.claude/agents/` and
`.claude/commands/`; ZCode reads the `.zcode/commands` symlink. A consumer
project mounts this tree (its `.agents/` may even be a symlink into a shared
checkout) and keeps its own local overrides in `.agents.local.toml` at the
repo root.

## Core Principles

1. **Agent-First** — Delegate to specialized agents for domain tasks
2. **Test-Driven** — Write tests before implementation; 80%+ coverage is a tracked health indicator, never itself a reason to add a test (see `.agents/rules/auto-skills.md`)
3. **Security-First** — Never compromise on security; validate all inputs
4. **Immutability** — Always create new objects, never mutate existing ones
5. **Plan Before Execute** — Plan complex features before writing code

## Available Agents

| Agent                       | Purpose                                | When to Use                                      |
| --------------------------- | -------------------------------------- | ------------------------------------------------ |
| detailed-plan               | Implementation planning                | Complex features, refactoring                    |
| architect                   | Solution selection and gating          | Architectural decisions                          |
| tdd-guide                   | Test-driven development                | New features, bug fixes                          |
| security-reviewer           | Vulnerability detection                | Before commits, sensitive code                   |
| py-antipattern-specialist   | Python antipattern and typing compliance | Pyright, typing contracts, and antipattern rules |
| sdd-implementer             | Task-level TDD implementation          | Parallel SDD task dispatch within worktrees      |
| sdd-reviewer                | Group-level code and spec review       | Parallel SDD post-group review within worktrees  |
| plan-scout                  | Read-only codebase reconnaissance      | Plan scouting, file mapping, architecture research|
| dimension-reviewer          | Dimension-specific plan review         | Detailed plan review across specialist dimensions|
| incident-debugger           | Root-cause debugging and diagnostics   | Failure analysis, stack traces, bug reproduction |
| diff-scout                  | Git diff and change analysis           | Commit message authoring, PR diff review         |
| code-reviewer               | Diff review against AGENTS.md and rules | Scoped git diff audits, pre-merge review         |
| silent-failure-hunter       | Silent-failure detection in code paths | Swallowed exceptions, unawaited coroutines, unhandled rejections |
| pr-test-analyzer            | Test-quality audit of changed test files | Assertion strength, edge-case coverage, mock isolation |
| type-design-analyzer        | Type-design review for encapsulation and invariants | New or changed type declarations in a diff       |
| comment-analyzer            | Comment and docstring accuracy audit   | Stale comments, misplaced findings in a diff     |
| code-simplifier             | In-place complexity reduction, behavior preserved | Simplifying files a reviewed change already touched |

## Agent Orchestration

Dispatch every independent, non-overlapping role in a single wave — one
subagent per problem domain, all issued in the same response so they run
concurrently. **Cap: at most N concurrent agents**, background or foreground,
read-only or writing — a read-only agent consumes the same quota as a
writing one, so no workflow exempts itself on that basis. N's single
machine-readable owner is `.agents/config.toml` (`[worktrees]
max_concurrent`, the same cap that bounds on-disk agent worktrees under
`.agents/worktrees/`); `.agents/scripts/worktree_acquire.py` and the Claude Code
hook backstop read it via `agentic_workflows.worktree_capacity`. Agents never
change N. When a wave has
more than N roles, dispatch in batches of ≤ N — a queue size, not a wait
trigger: a queued batch starts as soon as a slot frees (one completion or
one merge), never only after the whole running batch drains. Split into a
second wave only when a later role's scope genuinely depends on an earlier
wave's output, not merely because the role count is high. Give each
dispatched role an explicit scope, read/write permission, and expected
output shape so results merge cleanly. The lead owns final synthesis:
reconciling findings, resolving disagreement from source, and the resulting
write plan.

Use agents proactively without user prompt:

- Complex feature requests → **detailed-plan**
- Bug fix or new feature → **tdd-guide**
- Architectural decision → **architect**
- Security-sensitive code → **security-reviewer**
- Unknown root cause / incident postmortem → **root-cause-analysis**

Use subagents extensively for complex work when scopes are independent —
dispatch every independent role in one wave.

### Subagent Dispatch

- **Claude Code:** Dispatches specialist subagents via `/agent <name>` or automatic delegation based on frontmatter `description` and `tools`.
- **ZCode:** Dispatches the same specialist prompt sources directly from `.agents/specialists/<name>.md` via its subagent tooling; the frontmatter `tools:` and `description:` fields carry the same meaning as for Claude Code.

## Product Persona

If `docs/USER_PERSONAS.md` exists in the consumer project, read it first and
use it for product-facing decisions; otherwise proceed without it. When it
exists, workflows must evaluate what the user tried to do, what they saw,
what state is safe, and what they should do next before optimizing for
internal developer diagnostics.

## Security Guidelines

**Before ANY commit:**

- No hardcoded secrets (API keys, passwords, tokens)
- All user inputs validated
- SQL injection prevention (parameterized queries)
- XSS prevention (sanitized HTML)
- CSRF protection enabled
- Authentication/authorization verified
- Rate limiting on all endpoints
- Error messages don't leak sensitive data

**Secret management:** NEVER hardcode secrets. Use environment variables or a secret manager. Validate required secrets at startup. Rotate any exposed secrets immediately.

**If security issue found:** STOP → use security-reviewer agent → fix CRITICAL issues → rotate exposed secrets → review codebase for similar issues.

## Coding Style

**Immutability (CRITICAL):** Always create new objects, never mutate. Return new copies with changes applied.

**File organization:** Many small files over few large ones. 200-400 lines typical, 800 max. Organize by feature/domain, not by type. High cohesion, low coupling.

**Error handling:** Handle errors at every level. Provide user-friendly messages in UI code. Log detailed context server-side. Never silently swallow errors.

**Input validation:** Validate all user input at system boundaries. Use schema-based validation. Fail fast with clear messages. Never trust external data.

**Code quality checklist:**

- Functions small (<50 lines), files focused (<800 lines)
- No deep nesting (>4 levels)
- Proper error handling, no hardcoded values
- Readable, well-named identifiers

## Testing Requirements

**Coverage: 80%+ tracked as a health indicator, not a hard gate** — `.agents/workflows/detailed-plan.md` §5's Test Admission Gate governs which tests actually get written.

Test types (all required):

1. **Unit tests** — Individual functions, utilities, components
2. **Integration tests** — API endpoints, database operations
3. **E2E tests** — Critical user flows

**TDD workflow (mandatory):**

1. Write test first (RED) — test should FAIL
2. Write minimal implementation (GREEN) — test should PASS
3. Refactor (IMPROVE) — verify coverage 80%+

Troubleshoot failures: check test isolation → verify mocks → fix implementation (not tests, unless tests are wrong).

**Verification command:** a run's verification step executes the project's verify command, configured at `[project] verify_cmd` in `.agents/config.toml` — workflows read it from there and never restate the literal command.

## Development Workflow

0. **Harden the spec (when the task is ambiguous or risky)** — Run `/task-spec` to
   turn a vague ticket/task description into a precise, repository-grounded
   specification (behavior, authorization, data semantics, contracts) before
   planning. Skip for small, well-defined changes.
1. **Plan** — Use detailed-plan workflow, identify dependencies and risks, break into phases
2. **TDD** — Use tdd-guide agent, write tests first, implement, refactor
3. **Review** — Review the diff immediately, address CRITICAL/HIGH action items
4. **Capture knowledge in the right place**
   - Personal debugging notes, preferences, and temporary context → auto memory
   - Team/project knowledge (architecture decisions, API changes, runbooks) → the project's existing docs structure
   - User/persona assumptions and product-facing UX contracts → `docs/USER_PERSONAS.md` when it exists; otherwise the project's existing docs structure
   - Known bugs or open gaps (requires explicit user approval via a standalone, dedicated question) → the project's gap tracker (`.agents/open-gaps.md` where the project keeps one)
   - If the current task already produces the relevant docs or code comments, do not duplicate the same information elsewhere
   - If there is no obvious project doc location, ask before creating a new top-level file
5. **Commit** — Conventional commits format, comprehensive PR summaries

## Git Workflow

**Commit format:** see `.agents/workflows/commit-message.md` for the exact template — do not restate it here, one source of truth for the literal format.

**PR workflow:** Analyze full commit history → draft comprehensive summary → include test plan → push with `-u` flag.

**Worktrees:** create, release, and inspect them only through `.agents/scripts/worktree_acquire.py` (`acquire`/`status`/`release`), which enforces the on-disk cap N from `.agents/config.toml` — never a raw `git worktree add`; they live only at `.agents/worktrees/<name>`, a direct child of the main checkout — the one agent-owned root (a raw `git worktree add` anywhere else is blocked, and outside that root entirely is prohibited). Inside it, the usual worktree-scoped deny-list (`reset --hard`, `clean`, `restore`, `checkout`, `switch`, `bisect`, `update-index`, `stash drop`/`clear`, `tag -f`, `submodule --force`) is permitted. Force-removing a worktree and force-deleting a branch are separate and gated by target, not by standing inside one: `git branch -D` runs from anywhere as long as every named branch starts `sdd/`/`plan/` (a branch name is never a path, so `cwd` never affects it), and `git worktree remove --force` (same for `worktree add`'s target) is authorized as long as its `<path>` operand *resolves* to an agent-owned location — a bare relative operand resolves against the session's own `cwd`, so use an absolute path, or `-C <main-checkout-path>` plus a path relative to it (both work from anywhere *inside this repository*, not literally anywhere — the ownership anchor itself always follows the session's own actual working directory, never the `-C` value, so a shell outside the repo entirely still fails closed). `send-pack`, `config`, `remote` writes, `gc --aggressive`/`--prune`, and `reflog expire`/`delete` stay blocked everywhere; `push` keeps its own separate, unchanged canonical-form authorization (`git push -u origin HEAD:<branch>` only) either way — the parallel-SDD workflow's own push step relies on exactly this staying true. Full rule — the script-only creation rule, the durability invariant, and known gaps: `.agents/rules/agent-worktrees.md`.

## Architecture Patterns

**API response format:** Consistent envelope with success indicator, data payload, error message, and pagination metadata.

**Repository pattern:** Encapsulate data access behind standard interface (findAll, findById, create, update, delete). Business logic depends on abstract interface, not storage mechanism.

**Skeleton projects:** Search for battle-tested templates, evaluate with parallel agents (security, extensibility, relevance), clone best match, iterate within proven structure.

## Performance

**Context management:** Avoid last 20% of context window for large refactoring and multi-file features. Lower-sensitivity tasks (single edits, docs, simple fixes) tolerate higher utilization.

**Subsystem debugging:** Route work to the closest specialist first, then fall back
to **detailed-plan** or **architect** if the issue spans multiple domains.

## Project Structure

```
.agents/workflows/    — Canonical command prompt sources
.agents/specialists/  — Canonical specialist subagent prompt sources
.agents/skills/       — Reusable workflow skills and domain knowledge (skill-private prompts live in each skill's own folder)
.agents/rules/        — Shared rules and language-specific guidance
.agents/references/   — Shared grounding documents workflows cite
.agents/hooks/        — Repo-local Claude hook scripts (invoked as `python3 .agents/hooks/<name>.py`)
.agents/scripts/      — Workflow support scripts (invoked as `python3 .agents/scripts/<name>.py`)
.agents/config.toml   — Machine-readable tunables (worktree cap, verify command); human-owned
.agents.local.toml    — Consumer-local overrides; never written inside a shared checkout's .agents tree
agentic_workflows/    — The stdlib-only Python runtime the hooks and scripts import (agentic_workflows.*)
.claude/agents/       — Claude-native projected subagents (symlinks into .agents/specialists/)
.claude/commands/     — Claude-native projected commands (symlinks into .agents/workflows/)
.claude/skills/       — Claude-native projected skills
.claude/rules/        — Claude-native projected rules
.claude/settings.json — Claude Code hook wiring; every hooks[*].command points into .agents/hooks/
.zcode/commands       — ZCode projected commands (symlink into .agents/workflows/)
tests/                — Test suite, including projection validation
```

Claude Code reads the `.claude/` projections; ZCode reads `.zcode/commands`.
The canonical sources under `.agents/` remain the single place edits happen.

## Success Metrics

- All tests pass with 80%+ coverage
- No security vulnerabilities
- Code is readable and maintainable
- Performance is acceptable
- User requirements are met
