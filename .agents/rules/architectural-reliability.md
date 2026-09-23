---
trigger: always_on
---

# Architectural Reliability and Simplicity

For every non-trivial design:

1. Prefer the simplest design that satisfies the approved behavior.
2. Reuse established project patterns before introducing components,
   dependencies, abstractions, configuration, or mutable states.
3. Do not abstract around hypothetical variation. Abstract only around
   demonstrated reuse or a genuinely volatile/risky boundary.
4. Define the source of truth, ownership, lifecycle, invariants, and
   consistency expectations for affected data.
5. Define authorization for every state-changing or sensitive operation.
6. Minimize states and transitions. Avoid duplicated data and synchronization
   loops; derive values when practical.
7. Define atomicity, duplicate execution, retries, concurrency, cancellation,
   partial failure, and recovery for state-changing operations.
8. Validate untrusted input at boundaries. Fail closed for security-sensitive
   operations and preserve actionable diagnostic context.
9. Define timeout, rate-limit, unavailable, and degraded behavior for external
   dependencies.
10. Preserve compatibility with existing data and clients. Identify migration,
    rollback, and mixed-version behavior when relevant.
11. Make important success, failure, and recovery outcomes observable.
12. Specify how invariants, permissions, failure paths, and retry behavior
    will be verified.

Use enums for closed domains and data-driven identifiers for open-ended ones.
Use concurrency only when its value justifies its additional states and
failure modes.

Before accepting a design, ask:

- What is the simplest viable solution?
- What existing pattern can be reused?
- What new states, dependencies, and failure modes does this add?
- Can any failure be eliminated by construction?
- What happens after interruption, retry, duplication, or concurrent access?
- Who is permitted to perform each operation?
- How will migration, recovery, and verification work?
