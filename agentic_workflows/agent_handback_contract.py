"""The handback contract injected into every read-only subagent at
`SubagentStart`.

This module previously also carried a 15-tool-call turn budget. That budget
was withdrawn after it was measured rather than assumed: across 562 read-only
agents, tool calls per agent run to a median of 25 and a p90 of 48, so a
15-call cap truncated 75% of them. Truncation is not free -- the coordinator
re-dispatches against the "Not covered" gap, and the replacement agent pays a
fresh cold prefix, the single most expensive thing an agent does. A cap that
fires on three runs in four therefore buys roughly 1.75 prefixes where one
would have done.

The lever's 20.6% saving was a counterfactual replay that deleted every record
past turn 15 and re-priced. It proved the arithmetic, never that the work
still completed within the bound.

What survives is the half that costs nothing: an agent that stops early for
ANY reason -- a blocker, its own judgement, a budget some caller imposes --
should say what it did not reach. That makes an incomplete report honest
instead of indistinguishable from a complete one.

Stated limit, unchanged: `SubagentStart` is context-only. It cannot change a
subagent's model, tools, or prompt, and it cannot refuse the spawn. It makes
the instruction reliably PRESENT, not BINDING.
"""

from __future__ import annotations

# Read-only roles only. `general-purpose`, `workflow-subagent`, and
# `sdd-implementer` may edit files and are bounded by one-task-one-agent instead.
READ_ONLY_AGENT_TYPES = frozenset(
    {
        "Explore",
        "Plan",
        "code-reviewer",
        "diff-scout",
        "dimension-reviewer",
        "incident-debugger",
        "plan-scout",
        "sdd-reviewer",
    }
)

# Every `task-spec-*` agent is read-only by its own frontmatter description.
# The trailing separator is load-bearing: a bare `task-spec` prefix would
# also capture any future unrelated agent whose name merely starts with
# those letters.
READ_ONLY_AGENT_PREFIXES = ("task-spec-",)

# Deliberately states no call count. A number here would re-impose by
# suggestion the cap that measurement removed -- a dispatched agent cannot
# tell an injected budget from an advisory one, so "aim for about N" would
# land as the same truncation pressure the cap did.
_HANDBACK_CONTEXT = (
    "Your final report is bounded: use the shape your own role's output "
    "contract defines, not a running account of the work. If you stop before "
    "covering everything in your assigned scope -- for any reason -- name the "
    "exact surface you did not reach in a 'Not covered' section. An incomplete "
    "report that says what it missed is correct; one that reads as complete "
    "when it is not is a defect. Do not pad the run to look thorough, and do "
    "not stop early to look efficient."
)


def is_read_only_agent_type(agent_type: str) -> bool:
    """True when this agent type only reads and reports.

    Fails closed: an unrecognized type is treated as one that may edit, so a
    new implementer role never picks this up by accident.
    """
    if agent_type in READ_ONLY_AGENT_TYPES:
        return True
    return agent_type.startswith(READ_ONLY_AGENT_PREFIXES)


def build_handback_contract_context(agent_type: str | None) -> str | None:
    """The contract text to inject for this agent type, or None to inject
    nothing.

    None for a role that may edit, and None for an event carrying no agent
    type at all -- an unidentified agent is not one to instruct on a guess.
    """
    if agent_type is None:
        return None
    if not is_read_only_agent_type(agent_type):
        return None
    return _HANDBACK_CONTEXT
