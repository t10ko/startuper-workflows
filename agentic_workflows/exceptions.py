"""The minimal exception family the vendored modules share.

`FailLoudError` is the base for failures that must never be caught into a
fallback: the identical input violates the contract identically on a re-run,
so no retry, degrade, or default can turn it into a pass. Keeping the family
small and greppable under one name is the point.
"""

from __future__ import annotations


class FailLoudError(Exception):
    """Base class for errors that must surface, never be absorbed."""


class ContractViolation(FailLoudError, ValueError):
    """A deterministic violation of a contract this repository owns.

    An input, config, artifact path or stored shape that does not meet a
    contract this code states and enforces: the identical input violates it
    identically on a re-run. Also a `ValueError` so callers that net only
    `ValueError` around decode/validation boundaries still catch it.
    """


class EnvironmentFaultError(FailLoudError):
    """The surrounding environment failed a process (spawn, signal, I/O on a
    pipe) in a way that is not the child's verdict."""
