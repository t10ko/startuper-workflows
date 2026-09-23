---
trigger: glob
globs: "agentic_workflows/**"
paths:
  - "agentic_workflows/**"
---

# Spend Pricing Table Currency

`agentic_workflows/spend/owned_price_table.py` holds this repo's own pricing rows and
`agentic_workflows/spend/owned_pricing.py` the load gate and lookup that read them
— neither depends on LiteLLM's bundled table or an env-configured
`SPEND_PRICING_JSON` blob for the paths it covers. It is authoritative only as
long as every row stays accurate. Three standing obligations keep that true.

## The three obligations

1. **Monthly recheck.** Every row's `checked_on` date must be re-verified
   against its own `source_url` at least every 31 days, unless the row's
   period has already ended — a page that no longer states an identity's rate
   cannot be re-read, so such a row is outside the signal entirely.
   A **rate change closes the current row and opens a new one**: set the old
   row's `retired_on` and the new row's `introduced_on` to the same instant,
   and never edit a rate in place. Editing in place destroys the only record
   of what billed the money already recorded at the old rate.
2. **New model or provider lands its row in the same diff.** Adding a model
   to any configured LLM chain, or adding a new
   paid provider anywhere in the project's source,
   must add that model's pricing row to
   `OWNED_PRICE_TABLE` (`agentic_workflows/spend/owned_price_table.py`) in the same
   change — not as a follow-up. An absent row silently falls back to
   `pricing_source="unpriced"` (`agentic_workflows/spend/pricing.py`'s
   `estimate_provider_spend`), which is honest but means the spend ledger
   under-reports real cost from the moment that model starts being called.
3. **A retired identity keeps its row; it is never deleted.** When a model is
   deprecated or its source page stops stating its rate, close the row with a
   `retired_on` instant. Deleting it leaves every amount already recorded
   against that identity explainable by nothing at all, and blocks the whole
   ledger file from repair. This reverses the instruction that stood
   here until 2026-09-07, which said to remove the row: 187 recorded amounts
   were left unexplainable by exactly that.

## Row shape

`OwnedPriceRow` is a union of three kinds — a scalar-unit rate, a token rate,
and a declared-unpriceable identity — and the rate fields differ per kind. What
every row of every kind carries:

- `provider`, `model`, `operation` — the lookup triple, in the canonical
  spellings their owners resolve to.
- `audio`, `resolution_tier` — the billing dimensions that extend the identity
  where a vendor bills on them; `None` keys the vendor-default call, never
  "any value".
- `source_url`, `checked_on` — the provenance that makes the monthly-recheck
  obligation above mechanically checkable rather than aspirational. A row without a real,
  re-fetchable `source_url` cannot be re-verified, and must not be added.
- `introduced_on`, `retired_on` — **the period the rate applies over**, as
  instants in coordinated universal time. The start is closed, the end is
  exclusive, and an **absent end means "still applies"**. Two periods for one
  identity meet at one shared instant; a microsecond of daylight between them
  is a window no rate covers, and the load gate refuses the whole table for
  it at application start.
- `caveat` — a mispricing the identity cannot avoid, stated where a test can
  assert it, never only as a source comment.

Never ask `retired_on is not None` to mean "this rate is over". A rate on a
published dated schedule carries an end in the future while being the rate
billing right now. Ask the row: `applies_at`, `begins_after`, `has_ended`.

## Never fabricate a rate

If a provider's pricing cannot be found from an authoritative,
re-checkable source (their own pricing/docs page, not a third-party
aggregator or blog estimate), do not add a row with a guessed number. Leave the model unseeded — it falls back to `unpriced`, the existing honest
signal — and propose recording the gap in the project's own tradeoff/gap
doc, if it keeps one (asking
the user for explicit approval via a standalone, dedicated question first)
with what was tried and why no source qualified.

## Lookup semantics

`estimate_from_owned_table` matches on the exact `(provider, model,
operation)` triple, the billing dimensions where an identity's rows disagree
on them, **and the moment** — a required argument naming the instant the call
is being priced for. Only rows whose period covers that instant are
candidates, so an identity holds one row per period and which one answers is
never decided by the order the table lists them in. Every recording seam
passes the same instant it stamps its own row with.

There is no provider-only or operation-only fallback within the owned table —
an unspecified or unrecognized model, or one whose committed periods do not
cover the moment, simply does not match, and `estimate_provider_spend` falls
through to `SPEND_PRICING_JSON`'s coarser provider+operation rules next, then
to `unpriced` if neither source has a row.

**Pricing a new call and explaining an old amount are different questions.**
The lookup answers only the first: which rate *applies* at this instant. A
repair asking which rate *produced* an already-stored figure must consider
rows whose period does not cover the record, because a rate wrongly applied is
exactly a rate that did not apply. Never route that question through
`applies_at`.
