# Orchestration and parallelism

This reference belongs to the task-spec workflow's multi-agent coordination mechanics — read it when dispatching, delegating to, or coordinating any specialist subagent or workflow, or making any fan-out/fan-in or checkpoint decision.

## Orchestration and parallelism

The main conversation is the **spec coordinator**. It owns user interaction, decisions, synthesis, and the specification file.

### Single-writer rule

- Only the coordinator may create or edit the specification document.
- Every subagent and workflow worker is read-only.
- Workers return findings; they never modify any file.
- Do not delegate user questions. `AskUserQuestion` belongs to the coordinator.
- Do not use worktrees for this workflow.

### Preferred specialist subagents

Use these when installed and relevant:

- `task-spec-discovery-scout`: current behavior, terminology, constraints, tests, schemas, interfaces, evidence, and failure-class sibling sweeps for defects.
- `task-spec-contract-analyst`: actors, state flows, transitions, authorization matrices, data semantics, lifecycle, UI/accessibility requirements, and prompt-authoring compliance with the project's documented prompt rules.
- `task-spec-risk-analyst`: security, privacy, abuse, dependencies, failure modes, concurrency, compatibility, operational risk, candidate approach generation, and decision evaluation.
- `task-spec-adversarial-critic`: specification-quality audit (ambiguity, contradiction, testability, traceability, literal loopholes) and implementation-readiness simulation.

These specialists are expected to be registered in this repository. If a named specialist is unavailable, state that once — it signals a registration gap, not an expected state — then continue with a built-in read-only Explore subagent or a focused read-only substitute operating under the same brief file at `.agents/skills/task-spec/agents/<role>.md` (e.g. `.agents/skills/task-spec/agents/discovery-scout.md`). Do not abandon the workflow because a custom agent is missing. When the fallback dispatches a built-in read-only Explore agent rather than a registered specialist, the delegation prompt carries that brief's repo-root-relative path, instructs the worker to read it first and operate under it, and states the repository root so the path resolves without a cwd assumption.

### Delegation context package

Every delegation prompt must include only what the worker needs:

- concise task statement and source;
- current specification path, if it exists;
- accepted and tentative decisions relevant to the assignment;
- relevant repository areas already identified;
- the assigned lens, given as the brief file path — `.agents/skills/task-spec/agents/<role>.md`, repo-root-relative with the repository root stated so it resolves — never as inlined brief text;
- required compact output shape;
- explicit read-only/no-edit instruction;
- `If you stop before covering everything in your assigned scope — for any reason — name the exact surface you did not reach in a "Not covered" section. An incomplete report that says what it missed is correct; one that reads as complete when it is not is a defect.`

The coordinator itself never reads or inlines brief text: the brief reaches the worker either as a registered agent type's own definition (harness-loaded) or as the brief path in the list above, which the worker reads first.

**Do not put a tool-call budget in a delegation prompt.** A cap truncates most read-only agents before they finish, and truncation is not free, because the coordinator re-dispatches against the gap and the replacement pays a fresh cold prefix, the most expensive thing an agent does — more than the cap saves. Measurement history: design-notes.md §The delegation tool-call budget measurement.

The handback contract survives that removal on its own merit, because it costs nothing and makes an incomplete report honest. `.agents/hooks/inject_subagent_handback_contract.py` injects it at `SubagentStart` for every `task-spec-*` type, so it arrives even when a delegation prompt omits it — that hook is context-only and cannot bind an agent to anything, so keep the line in the prompt too.

Require workers to label claims as:

- `Confirmed`: supported by task text or repository evidence;
- `Inferred`: reasoned but not directly established;
- `Unknown`: material gap;
- `Recommendation`: advisory, not a settled requirement.

Require durable evidence such as relative paths, symbols, tests, schemas, or document sections.

### Fan-out and fan-in

When investigations are independent:

1. Launch them concurrently.
2. Collect all results before asking the first substantive question.
3. Deduplicate overlap.
4. Resolve disagreements with evidence.
5. Convert unresolved, material disagreements into one user decision at a time.
6. Integrate only supported findings.
7. Never paste raw reports into chat or the spec.

Use the smallest useful panel. **Max N concurrent agents** per `.agents/AGENTS.md`'s Agent Orchestration section (N from `.agents/config.toml`, `[worktrees] max_concurrent`) — when a stage triggers more than N relevant specialists, dispatch in batches of ≤ N, a queued batch starting as soon as a slot frees (one completion or one merge), never only after the whole running batch drains.

### Orchestration checkpoints

1. **Discovery checkpoint** — before the initial draft.
2. **Decision checkpoint** — for one consequential unresolved choice.
3. **Behavioral audit checkpoint** — on a decision that changed a section a specialist owns.
4. **Engineering-readiness checkpoint** — after behavioral requirements are stable and before completion.
5. **Final audit checkpoint** — after material corrections.

At each checkpoint, the coordinator emits a lightweight status readout — current stage, specialists in flight or completed, and remaining open items — so the user is never left without progress visibility during a long discovery or audit stage. Recognize a `status` or `progress` keyword from the user as an on-demand request for this readout.

Do not fan out after every answer. Re-run specialists only when an answer materially changes scope, permissions, state semantics, data semantics, contracts, failure behavior, or design constraints.

### Optional dynamic-workflow mode

Use dynamic workflows only for bounded, read-only discovery or audit work involving many independent checks. Do not use them for the interactive question loop.

When `--workflow` is active and workflows are available:

- use one workflow for broad initial discovery when justified;
- use a separate workflow for the final adversarial audit;
- require one compact, deduplicated report;
- keep every worker read-only;
- return to the main conversation for synthesis and `AskUserQuestion`;
- fall back to normal subagents if workflow execution is unavailable or excessive.

