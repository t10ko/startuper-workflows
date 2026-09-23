"""Vendored, stdlib-only runtime for the agentic-workflow system.

Every module here runs on the Python standard library alone (3.11+), because
consumers install this system into arbitrary-language repos and invoke hooks
and scripts with plain `python3` — no venv, no dependency install step. Two
modules are functional rewrites of pydantic-backed originals
(`review_loop_iterations`, `worktree_capacity`, `review_fix_partition`,
`instructions_loaded_log`) with identical validation semantics; `secret_scan`
is a heuristic scanner with the same public API a `detect-secrets`-backed
implementation could drop in behind.
"""
