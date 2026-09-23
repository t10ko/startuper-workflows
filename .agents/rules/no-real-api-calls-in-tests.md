---
trigger: glob
globs: "tests/**/*.py"
paths:
  - "tests/**/*.py"
---
# No Real API Calls in Tests

Tests must never make real outbound network or provider API calls. They must
run for free and work with no network access, every time, in any order.

## The rule is not just "mock the provider"

The sharp version: any test whose exercised code spawns work that outlives the
test's own function body — a background thread, a detached task, a
fire-and-forget job — can silently defeat **every** mock in that test **and**
the suite's global network-blocking safety net (autouse fixtures in the
conftest that block outbound sockets and paid provider SDKs). Those guards
are `monkeypatch`-based and torn down the instant the *requesting test
function* returns — they cannot catch a real call made by a background thread
that is still running after that.

## The incident that surfaced this

Enabling parallel test execution (2026-07-13) exposed a test that crashed
roughly 1 run in 4 with a real, unmocked provider API call deep inside a
third-party async networking library. Root cause: a background-job runner
(`start_isolated(job_id, coroutine)`-style) ran its coroutine on a
**separate OS thread with its own fresh event loop**
(`asyncio.to_thread(...)` → `asyncio.run(...)`), fire-and-forget. A test
patched the orchestrated component only for the duration of an HTTP call,
then let the `with patch(...)` block close and the test function return. The
background thread hadn't run yet; once the patch was undone, it read the real
class and made a real network call. Because it ran on an unrelated thread,
pytest's built-in unraisable/thread-exception capture attributed the crash to
whatever *other* test happened to be running at that instant — making the
failure look random and misattributed.

A raw exception from deep inside the networking library (instead of the
network guard's own clean assertion failure) shows that a connection attempt
reached the library; it does not show that the guard had already been
torn down. Read from the library source and one mutation trace (not reproduced
in isolation), a connection made while the guard is still active ends in the
library's own error and the guard's own message is lost, because the
library records only `OSError` and `RuntimeError` failures. Tell the two cases
apart by whether background work outlived its test, not by the error's shape.

## What to do when writing or reviewing a test

If the exercised code path can reach a fire-and-forget job runner (a
`start_isolated`-style helper),
`asyncio.create_task`, `asyncio.to_thread`, `threading.Thread`, or any other
fire-and-forget background execution:

- Prefer replacing the spawn call itself with a synchronous stub in that test
  (e.g. patch the runner with `side_effect=lambda job_id, coro: coro.close()`)
  when the test doesn't need the spawned work to actually run.
- Otherwise, explicitly await the spawned work to completion before the test
  function returns and before its mock/patch context managers close. If the
  suite provides a shared helper that awaits an isolated job by id, call it
  right after the HTTP call returns, still inside the `with
  patch(...)` block.
- Never rely on implicit timing luck for a background thread/task to finish
  "in time."

## Why a grep of the test file is not enough

The actual spawn call site is usually in *production* code (a route or
service), reached indirectly through an HTTP request the test makes — not
visible by grepping the test file itself. Look at what the exercised
route/service actually does, not just what the test file literally imports.

## Mechanical enforcement

An autouse conftest fixture can fail any test which leaves a background job
still running at its own teardown (an active-jobs registry still non-empty),
regardless of which production code
path triggered the spawn. This is the same kind of mechanical, non-optional
enforcement this repo already uses for other invariants (e.g. a check that
enforces dependency injection over monkeypatching) — a written rule alone is
not sufficient, because the failure mode here is silent and can hide for a
long time before parallel execution (or
bad luck) surfaces it.

## Existing infrastructure to reuse, not duplicate

- Socket-level outbound-network guards and paid-provider-SDK guards (autouse
  conftest fixtures) catch real calls made *synchronously within a test's own
  body*.
- A live-test marker (e.g. `@pytest.mark.live_api`) plus an opt-in CLI flag
  (e.g. `--allow-live-api`) is the only sanctioned way to write an
  intentionally
  live test. It is never enabled by default in any verify target, the
  pre-commit test hook, or CI — it is opt-in only, and as of this writing
  zero tests use it. (Corrected 2026-09-08 with the creator's approval: this
  file used to say the repo had no CI pipeline at all, which stopped being
  true when a CI pipeline landed. That pipeline runs the project's verify
  command (configured at `[project] verify_cmd` in `.agents/config.toml`),
  which does not pass `--allow-live-api`, so the statement it supported still
  holds.)
