# Questioning protocol

This reference belongs to the task-spec workflow's questioning framework — read it when a discovered question needs classifying, before opening `AskUserQuestion`, or before choosing between clarification and decision-workshop mode.

## Four levels of questions

Classify every discovered question before deciding whether to ask it.

### Level 1 — Behavioral requirement

Examples:

- Who may perform the action?
- What happens when the resource is expired?
- Is history retained or overwritten?
- What does the user observe after partial failure?

These MUST be resolved or explicitly left open. They belong in the specification.

### Level 2 — Data or external contract

Examples:

- Identity, ownership, cardinality, uniqueness, lifecycle, retention, and consistency semantics.
- Request/response fields, event meaning, error categories, idempotency behavior, and compatibility promises.

These MUST be resolved when relevant. They also belong in the specification.

### Level 3 — Engineering design decision

Examples:

- Separate relational table versus JSON/embedded representation.
- Transaction boundary or outbox strategy.
- Synchronous versus asynchronous integration.
- Index strategy derived from required access patterns.
- Fixed pattern, threshold, or rule versus a judgment-based mechanism that generalizes across the system's known input diversity.
- Configuration or feature-flag strategy for rollout and reversibility.
- Caching strategy, including staleness tolerance, invalidation trigger, and key scope.
- Asynchronous or background-job execution model, including spawn semantics, buffering or chunking, and detached-versus-awaited behavior.
- Cost or rate-limit budget strategy for a paid or throttled dependency.

Resolve these in adaptive or `--design` mode only when the choice is materially coupled to correctness, security, data lifecycle, compatibility, scale, migration, or operations. In `--requirements-only` mode, record them under **Open engineering decisions** instead.

### Level 4 — Local implementation discretion

Examples:

- Function names.
- Private helper structure.
- Exact source files.
- Small refactors.
- Equivalent library calls.

Do not ask the user about these and do not let them block specification readiness.

When uncertain between levels, ask: **Would two implementations that choose differently still satisfy the same observable contract and important engineering constraints?** If yes, it is probably Level 4. If not, it belongs earlier.


## Mandatory structured question UI

The coordinator MUST use Claude Code's `AskUserQuestion` tool for every clarification, choice, approval, or workshop answer whenever available.

- Ask exactly one question per call.
- Do not duplicate the question in normal prose.
- Save the specification before opening the UI.
- **Zero-ID Question Header**: Use a concise, descriptive domain header. Strictly DO NOT include the specification's internal tracking IDs (requirement, flow, edge-case, decision, or question IDs) in question headers, question text, or selectable options.
- **Unified Plain-Language Context Block**: Frame the question with a single plain-language paragraph (2-3 sentences) answering what the component is, why it matters, and the current operational situation without unexplained technical jargon.
- **Symmetric Outcome-Based Options**: Format every option as `[Action] — [Operational Impact/Tradeoff]`. Provide two to four genuinely distinct options when choices are discrete.
- Put the best-supported option first and mark it `(Recommended)`.
- Preserve the custom/Other answer path.
- Use `multiSelect: false` unless options are truly independent.
- Treat an empty or cancelled result as no answer; do not re-ask immediately. Keep the item open and re-surface it later or in the final unresolved list.
- Only the coordinator may call `AskUserQuestion`.
- If the tool is unavailable, state that once and fall back to one concise plain-text question.

After an answer:

1. Interpret only the selected option or custom text.
2. Disambiguate the same item if needed.
3. Update the spec, decision log, requirements, flows, matrices, edge cases, and acceptance criteria before asking anything else.

## Conversation modes

### Clarification mode

Use for missing facts and straightforward choices.

- Keep prose before the UI under 120 words when practical.
- State a recommendation when evidence supports one.
- Present the Bounded Context Triad and symmetric options via `AskUserQuestion` without exposing internal document IDs.
- Ask one precise question.
- Integrate the answer immediately.

### Decision-workshop mode

Use when a decision is consequential, hard to reverse, data- or security-sensitive, or involves real tradeoffs.

Enter when:

- `--workshop` is supplied;
- the user says `workshop`, `go deep`, or similar;
- several credible options remain after research;
- the choice affects multiple flows, actors, states, contracts, or data constraints.

On first workshop entry per session, state the in-workshop commands (`panel`, `challenge`, `compare A and B`, `recommend`, `accept`, `park`, `normal mode`) and the exit commands (`finish spec`, `done`, or `stop`) once, so the mode's controls are disclosed rather than left implicit.

For one active decision:

1. Record internal tracking ID (e.g. `D-003`) in the specification document for auditing, but omit raw IDs from user-facing prompts.
2. State the decision and why it matters using the Bounded Context Triad.
3. Identify decision criteria.
4. Compare two to four credible options.
5. Surface strongest benefits, costs, failure modes, hidden assumptions, reversibility, and second-order effects.
6. Give a recommendation and confidence when supportable.
7. Ask one UI question that advances the decision using symmetric outcome-based options.
8. Stay on the same decision until accepted, parked, or sufficiently understood.
9. Distinguish `Open`, `Tentative`, `Accepted`, and `Parked`.

After four exchanges on one decision, give a compact recap:

```markdown
Established: ...
Still uncertain: ...
Current leaning: ...
```

The user may say:

- `panel` — run a three-lens decision panel;
- `challenge` — present the strongest case against the current leaning;
- `compare A and B` — deepen only that comparison;
- `recommend` — make the best-supported recommendation and ask for acceptance;
- `accept` — finalize the current decision;
- `park` — record it unresolved and move on;
- `normal mode` — return to clarification mode.

