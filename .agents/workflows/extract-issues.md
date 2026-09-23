---
description: Extract issues from the given logs (issues, warnings, logical problems)
---

Analyze the provided logs and extract all errors, warnings, and potential logical anomalies. For each identified problem, provide a brief explanation of the issue and propose an actionable solution.

If `docs/USER_PERSONAS.md` exists, use it when prioritizing issues and treat
the operator personas it defines as the user-impact lens; otherwise proceed
without it and prioritize by user-visible impact directly. Failures a user
can see or be misled by — hidden backend failures, blank outputs, stale
progress, unclear approval state, or implementation-heavy UI copy — are
product failures, not only technical failures.

CRITICAL ARCHITECTURAL CONSTRAINT: Actively scan the logs for any operations
executing across the whole input scope at once (for example, whole-scope
parameter extraction during per-unit processing). Where a project's
architecture mandates unit-scoped processing, whole-scope processing is
strictly forbidden. If any whole-scope operations are detected, you must
explicitly, prominently, and unambiguously flag them as critical violations
and prioritize refactoring them in your proposed plan.

MANDATORY DEEP DIVE: The provided logs are only a starting point. You must explicitly search for and cross-reference the more detailed application log files within the project. Use these deep logs to determine the true root cause of what happened before finalizing your proposed solutions.

For large or multi-surface failures, follow
`.agents/AGENTS.md` and run extraction waves. Wave 1:
`AppLogExtractor`, `DetailedLogExtractor`, and `RuntimeStateExtractor`.
Wave 2 when needed: `WarningAnomalyExtractor`
plus any targeted source/log scout. Projects can register additional
extraction waves for their own whole-scope violation rules (see
extract-issues.md's wave pattern). The lead owns main-issue priority, final
grouping, and root-cause ranking.

Prioritize the main issue by combining user-visible impact with root evidence:
what the user tried to do, what they saw, what state became unsafe or unclear,
and which source layer must be fixed to prevent recurrence.
