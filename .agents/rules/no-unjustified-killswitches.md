# No Unjustified Killswitches or Feature Flags

Recorded 2026-09-09 at the user's explicit request, after removing a speculative feature flag that guarded active core behavior without an operational deployment requirement.

## The rule

A feature flag, killswitch, or configuration toggle must have a **real, stated operational reason**. Introduce one only when you can name the concrete runtime or operational condition that requires toggling or disabling the feature in production (such as a costly external API dependency, an unverified upstream provider integration, or an explicit human-in-the-loop operational rollback requirement). If you cannot name that operational condition, do not add a killswitch or flag — execute the behavior directly and let the system fail fast.

This is not a ban on feature flags. It is a ban on speculative flags and defensive killswitches that exist merely as hypothetical safety nets or habit.

## Why, in the project's own terms

This codebase follows strict MVP contracts (AGENTS.md §1: "No backward compatibility, shims, or dual-paths. Replace contracts immediately across producers, consumers, and tests in the exact same diff. Fail fast on bad input.").

Speculative killswitches and flags introduce significant hidden costs:
- **Dead dual-paths**: Every toggle creates two branching execution paths across the application and tests. The disabled path is either completely untested or tests mock/dead behavior that will never run in production.
- **Contract dilution**: Wrapping a required invariant or core pipeline stage in a toggle obscures what the system's actual contract is, encouraging callers and tests to bypass errors rather than resolving them.
- **Configuration rot**: Toggles accumulate in the project's configuration files and config modules, bloating configuration, increasing cognitive parse time (>15s rule), and leaving obsolete flags long after the feature is stable.

Default behavior must run directly and unconditionally. If a new architectural feature or mechanical gate is accepted, it replaces the old contract outright.

## How to apply

Before introducing a feature flag or killswitch in the project's configuration, answer all three:

1. **What concrete operational condition requires disabling or toggling this feature at runtime?** Name it. "In case something breaks" or "for safety during rollout" is not sufficient in an MVP codebase unless an actual gradual rollout infrastructure or multi-tenant deployment exists to leverage it.
2. **Who or what will toggle the flag, and how?** If no operator, automated canary, or environment distinction ever sets it to anything other than its default, the toggle is dead code.
3. **What is the consequence when the flag is disabled?** If disabling the flag reverts to broken, incompatible, or untested behavior, the switch is an illusion of safety that conceals regressions rather than managing risk.

If all three have concrete operational answers, declare the setting in the project's configuration and document its operational lifecycle. If any one does not, omit the toggle and execute the behavior unconditionally.

## Related rules

- `AGENTS.md` §1 MVP Contracts — "No backward compatibility, shims, or dual-paths. Fail fast on bad input."
- `.agents/rules/no-unjustified-fallbacks.md` — a fallback must not substitute for establishing what the contract actually is.
- `.agents/rules/architectural-reliability.md` — Prefer simplicity; minimize states and transitions; eliminate failure by construction.
