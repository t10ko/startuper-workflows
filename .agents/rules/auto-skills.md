---
trigger: always_on
---

# Always-Active Skills

These skills are always in effect for this project. Their principles apply to every task without needing to be invoked explicitly.

---

## tdd-workflow

Always write tests before implementation.

- RED: write a failing test that targets the real behavior
- GREEN: implement the simplest code that makes it pass
- REFACTOR: only after green, only if needed for clarity, always reducing cognitive load
- 80%+ coverage (unit + integration) is a tracked health indicator, never itself a reason to add a test — `.agents/workflows/detailed-plan.md` §5's Test Admission Gate is the sole authority on which tests get written; a plan may ship below 80% when every remaining gap fails that gate
- Never mock the function under test — only mock external boundaries (network, disk, time)
- No placeholder/stub production code just to make tests compile
- Never let a test make a real network/provider API call. Any test whose exercised code spawns background async work (thread, task, fire-and-forget job) must await it to completion before the test returns, or it can escape every mock and the global network guard — see `.agents/rules/no-real-api-calls-in-tests.md`

Run: `python3 -m pytest`

---

## python-testing

- Framework: **pytest** only. No `unittest.TestCase`.
- Test functions, not classes.
- Use `tmp_path`, `monkeypatch`, and `pytest.fixture` for isolation.
- `@pytest.mark.unit` for fast tests, `@pytest.mark.integration` for external deps.
- No trivial tests — every test must prove a real behavior.

Run: `python3 -m pytest --cov --cov-report=term-missing`

---

## python-patterns

- Type hints on all public functions and methods.
- Use `isinstance()` not `type() ==`.
- No mutable default arguments (`def f(x=[])` → `def f(x=None)`).
- Use `"".join()` not string concatenation in loops.
- `value is None` not `value == None`.
- No shadowing builtins (`list`, `dict`, `str`).
- `from agentic_workflows.logger import logger` — never `print()`.
- Import order: stdlib → third-party → local. Remove unused imports.
- Never run inline Python snippets via `python3 -c` or `python -c` in shell commands. Write scratch or test scripts to files under `verify/` and run them with `python3 verify/<script>.py`.

---

## security-review

Before every commit, verify:

- No hardcoded secrets (API keys, tokens, passwords) — use env vars
- All user inputs validated at system boundaries
- No f-strings in SQL queries — parameterized only
- No `eval()`, `exec()`, or unsafe deserialization
- No `yaml.load()` without `Loader=yaml.SafeLoader`
- Subprocess calls use list args, not shell=True with user input

If a security issue is found: STOP, fix CRITICAL issues before continuing.

---

## verification-loop

Verification cadence:

- Do not run full-suite verification after every code change.
- During iteration, run the narrowest relevant check for touched files or subsystem.
- Prefer targeted lint, type, or test commands while refining one file or one feature slice.
- Run the project's verify command (configured at `[project] verify_cmd` in `.agents/config.toml`) once at the end before handoff, review, or commit.
- If final full-suite verification fails, fix errors before proceeding.
- **This binds whoever writes a task brief, not only whoever writes code.** A
  brief that instructs a subagent to run the whole suite, or to measure a
  "baseline" by running it a second time, imposes the cost these rules exist
  to avoid — whatever the rules say elsewhere. Per commit, the pre-commit gate
  already selects only the tests the staged change reaches and needs no
  hand-written duplicate; per task, one full-suite run at most, and only when
  the change's blast radius warrants it.
- **Lint and type-check always; run the full test suite conditionally.** They
  are not one budget. Ruff, prettier, eslint and pyright read the tree without
  executing it, cost seconds, and catch a whole class of error the narrow
  per-commit test selection provably cannot see — an unused import, a broken
  annotation, a reference to a symbol a sibling task deleted. Running the
  entire test suite costs minutes and is only worth it when the change can
  reach code no selected test imports. Never defer a linter to save time, and
  never run the full suite merely because a linter was cheap.
- **A green result is assurance only over the population the artifact
  states.** Every verification artifact — a check, gate, or audit whose
  green result is read as assurance — must state, beside itself or in its
  disclosure, the population it does not reach. Nothing can mechanically
  detect "the population a name implies" in general, so whoever reviews a
  green run checks that stated reach and never treats the artifact's name
  as reaching more than the statement says.

---

## response-contract

The shape of every message sent to the user.

- Owned entirely by [.agents/rules/response-contract.md](.agents/rules/response-contract.md) as a single authoritative file. Its companion scope and formatting files are consolidated or deleted.
- This section deliberately states no rules of its own. It replaces the former `brief-chat` and `conversational` sections, which contradicted each other on reply length and mandated the process narration the contract now forbids.

---

## force-critical-thinking

Always-on adversarial posture and sycophancy mitigation.

- **Bypass Ego-Protection:** Evaluate all user requirements, designs, and code proposals in the third person as an unverified "claims package" submitted by a third party. Do not use ownership-based framing ("your code").
- **Friction-First Demeanor:** Eliminate introductory praise, conversational filler, emojis, and emotional validation. Deliver critiques directly, without softening them to protect feelings. This bans *social* hedging, never *epistemic* hedging: calibrated uncertainty, caveats, and "unverified for the general case" flags are required by `.agents/rules/no-overfitted-fixes.md` and must never be stripped for tone.
- **Anti-Sycophancy Constraints:** Suppress direct agreement markers ("Yes", "Agree", "True") at the beginning of generations. Use structural semantic pivots ("Conversely", "However", "But") to establish analytical distance.
- **Auditor Mindset:** Assume the role of a Lead Systems Auditor and Security Penetration Tester. Prioritize systemic correctness over politeness. Always verify codebase claims against the local file system.

---

## architectural-reliability

Enforce simplicity and design-time fault avoidance for all architectural decisions.

- Follow [.agents/rules/architectural-reliability.md](.agents/rules/architectural-reliability.md) strictly.
- Always use the Architectural Pruning Checklist before proposing designs or writing features.
- Avoid speculative abstraction: write concrete, direct code, and only abstract when there are at least three active use cases.

---

## no-overfitted-fixes

Any fix for a confirmed, generally-scoped problem must be designed at that same general level —
not narrowed to match only the current test data's specific formatting or convention.

- Follow [.agents/rules/no-overfitted-fixes.md](.agents/rules/no-overfitted-fixes.md) strictly.
- Distinct from `architectural-reliability`'s anti-speculation stance, not in tension with it:
  that rule blocks building for merely-hypothetical future needs; this rule blocks under-building
  for variation that is already certain (e.g. "this pipeline ingests arbitrary user documents" is
  a stated fact today, not a hypothetical).
- Before shipping a fix, ask: would this work on differently-formatted input I haven't tested —
  different language, different convention, different structural style? If the honest answer is
  "no, only because of how this project's current data looks," reach for a judgment-based
  mechanism (e.g. an LLM call reading real content) instead of a fixed text pattern or regex.

---

## brainstorming

Calibration for `.agents/workflows/deliberation.md`, this repo's own
decision-making workflow — usage notes for running it here.

- Scale in-chat approval to design complexity: for a small, coherent design,
  skip section-by-section approval in chat and gate on the written
  deliberation note alone — this repo's own HITL rule says "bothering the
  user should be just when absolutely necessary."
- Treat inherited/unchanged subsystem behavior as a design surface, not a
  silent default: when a design leaves an existing behavior (stage ordering,
  failure semantics, etc.) untouched, name that choice explicitly in the
  deliberation note as a confirmed decision rather than letting it pass by
  omission.

---

## memory

Project memories live in `MEMORIES.md` at the project root.

- Consent requirements for writing to `MEMORIES.md` (or any other standing
  record) are defined once, canonically, in `.agents/rules/memory-consent.md`
  — follow that rule.
- At the start of any task, **silently read** `MEMORIES.md` and apply matching
  rules. Do not announce the scan unless a memory directly changes visible
  behavior.
- See `.agents/skills/memory/SKILL.md` for full protocol.
