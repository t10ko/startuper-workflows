# Grounding artifact freshness

A grounding artifact — `docs/specs/grounding/<spec-slug>.md`, written once by
`task-spec-discovery-scout` — carries the file inventory, symbol map, and
excerpts every later stage reads instead of re-reading source. It is
trustworthy only while the files it cites are unchanged, so its freshness is
established before its body is read, never after.

**This file is the single owner of that protocol.** `task-spec`,
`detailed-plan`, and `parallel-subagent-driven-development` each point here
instead of carrying their own copy — the three copies this file replaced were
byte-identical, and a fourth reader would have made a fourth. The exit codes
themselves are defined by `.agents/.agents/scripts/spec_staleness.py`'s module docstring; this
file owns only what an agent does with each one.

## The protocol

**Grounding freshness — run the checker before reading any grounding artifact body:**

```bash
python3 -m scripts.spec_staleness docs/specs/grounding/<spec-slug>.md
```

Exit `0` — every cited file is unchanged since the anchor; read the body and use it as written. Exit `1` — a cited file is modified or deleted, or the artifact carries no anchor; demote every claim tied to a listed file to unverified, read source for exactly those files, and when the cause is no anchor, read source for every claim. Exit `2` — the anchor names a commit this history does not have, which is an error, not a verdict; read source for every claim.
