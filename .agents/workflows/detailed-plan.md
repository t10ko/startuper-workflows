---
description: Evidence-first implementation planning with evidence-gated discovery, failure-class coverage for bugs, minimal meaningful tests, and explicit integration gates.
---

# Detailed Plan Command Wrapper

This command launches the profile-routed TDD planning workflow defined in [.agents/skills/detailed-plan/SKILL.md](.agents/skills/detailed-plan/SKILL.md).

## Instructions

When `/detailed-plan` is invoked, execute the planning pipeline defined in [.agents/skills/detailed-plan/SKILL.md](.agents/skills/detailed-plan/SKILL.md):

1. **Profile Routing & Task Classification:** Determine profile (`COMPACT`, `STANDARD`, `ARCHITECTURE`, `INVESTIGATION`, `WORKFLOW_DOCS`) and tag task as `BUG` or `NON-BUG`.
2. **Evidence Preflight:** Inspect code, tests, diffs, and history. Check spec staleness when applicable.
3. **Evidence-Gated Discovery & Spec-Hydrated Fast Path:** Read [.agents/skills/detailed-plan/references/subagents.md](.agents/skills/detailed-plan/references/subagents.md). When an approved task spec is linked, use the Spec-Hydrated Fast Path to bypass Wave 1 discovery scouts and hydrate directly from the spec. Otherwise, for `BUG` tasks with no linked task spec, dispatch `FailureClassAnalyst`; when a spec is linked, verify its §5b sibling list instead. Dispatch other Wave 1 scouts ONLY for unresolved preflight gaps, **at most N concurrent agents** per `.agents/AGENTS.md` (N from `.agents/config.toml`, `[worktrees] max_concurrent`) — batches of ≤ N when more trigger. Route Wave 1 scout briefs to the registered `plan-scout` specialist (or built-in read-only `Explore` agent). **These scout names are not registered agent types — never pass one as `subagent_type`.** Each is a prompt brief for `plan-scout` / `Explore`, so finding no such agent is expected and is not worth reporting.
4. **Lead Synthesis:** Reconcile findings, lock root cause/contract fix, and build de-duplicated scenario ledger.
5. **Test Admission Gate:** Apply the 8-check admission gate. Determine integration test necessity (`REQUIRED` | `NOT REQUIRED`).
6. **Conditional Wave 2 Review:** Run `TestMinimalityCritic` and `IntegrationAdequacyCritic` via the registered `dimension-reviewer` specialist (or built-in read-only `Explore` agent) ONLY if candidate shortlist >6 tests or boundaries are disputed.
7. **Output Schema & Execution Grouping:** Render `implementation_plan.md` following [.agents/skills/detailed-plan/references/output_template.md](.agents/skills/detailed-plan/references/output_template.md) and [.agents/skills/detailed-plan/references/execution_grouping.md](.agents/skills/detailed-plan/references/execution_grouping.md) (identifying the critical path, isolating shared config/schemas into Wave 0 bootstrap, de-bloating blocking groups, and saturating concurrency up to the configured cap).
8. **Clean Handoff & Implementation Command:** Validate self-review checklist and present plan for human approval before entering [.agents/skills/parallel-subagent-driven-development/SKILL.md](.agents/skills/parallel-subagent-driven-development/SKILL.md). When the plan is ready to be implemented, the final response MUST provide next instructions including:
   - A recommendation to perform a context compaction (e.g., running `/compact` or compacting context) before starting execution.
   - The exact command in a standalone code block for easy copy-pasting, **always including all three execution-mode flags** so execution starts without re-asking the autonomy mode:
     ```
     /parallel-subagent-driven-development [REL_PATH_TO_PLAN] --dont-stop --dont-ask --dont-defer [OPTIONAL_ADDITIONAL_INSTRUCTIONS]
     ```
     *(substitute `[REL_PATH_TO_PLAN]` with the relative path to the plan file, e.g., `/parallel-subagent-driven-development docs/plans/<plan-filename>.md --dont-stop --dont-ask --dont-defer`; strip a flag only when the user explicitly wants that axis's default behavior)*.

**A plan is not a findings register.** Discovery surfaces problems the plan will not fix — a gap no task owns, a spec claim measurement contradicted, a value with two owners. None of it belongs in `implementation_plan.md`, in a task's `Produces`, or in a code comment: it goes in a decision note under `docs/decision-notes/`, per `.agents/rules/findings-go-in-decision-notes.md`. A plan states what will be done; a finding states what is wrong, and a reader who finishes the plan stops reading it.
