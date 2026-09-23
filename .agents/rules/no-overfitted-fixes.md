---
trigger: always_on
---
# No Overfitted Fixes

When fixing a confirmed problem, the fix itself must hold up across the
real range of input the system is already known to face — not just the
one example currently being tested against.

## The rule

If the problem you are fixing is general by the product's own nature
(e.g., "this pipeline ingests arbitrary user documents" — already true today, not
a hypothetical), the fix must be designed at that same level of
generality. A fix that only works because of how the *current* test
project happens to be formatted is not fixed — it has been made to pass
one example, and will silently fail the next document, the next language, or
the next convention that doesn't match it.

This is not the same claim as "avoid speculative abstraction"
(`.agents/rules/architectural-reliability.md`). That rule is about not
building for merely-hypothetical future needs that haven't been
demonstrated. This rule is the opposite case: the variation is **already
certain**, not hypothetical (arbitrary documents, arbitrary languages,
arbitrary formatting conventions are the product's stated scope right now) — so
narrowing a fix to only the current example's shape is under-building
for a need that already exists, not over-building for one that might.

## How to tell the difference before writing the fix

Ask: **would this fix work if the input were formatted differently —
different language, different formatting convention, different structural
style — even though I haven't tested that case?**

- If the honest answer is "no, this only works because of how this one
  project's data happens to look" — that is the failure this rule
  targets. Reach for a judgment-based mechanism (an LLM call reading the
  real content) instead of a fixed text pattern, or generalize the
  pattern's underlying logic, not just cosmetically loosen the regex.
- If the honest answer is "yes, because the mechanism reasons about the
  underlying concept, not this project's specific formatting" — the fix
  is appropriately general.

## What a constant may encode

A constant is not automatically an overfit. It may encode a decision
the project is entitled to make — a character budget, a retry cap, a
patience limit before falling back. Disclosing that kind as unverified
for the general case (see "How to apply" below) is a legitimate way to
ship it.

A constant may also encode a claim about something it is not entitled
to decide — a threshold asserting that a piece of writing, on one side
of some number, *is* one kind of content rather than another (a length
bound below which text *is* front matter rather than substantive
content, for instance). That kind is not a narrower version of the
fix; it is the wrong instrument at any value, because no number makes
the claim true — text either is or is not what the threshold says it
is, independent of which number was picked.

**Disclosing a narrow mechanism does not license it.** An investigation
into a structural-boundary detector found every author who proposed a
content-claiming constant disclosed its narrowness correctly in their
own write-up, and the mechanism still reached a recommendation anyway.
Correct
disclosure describes the flaw; it does not remove it.
The "flag it as unverified" step in "How to apply" below still holds
for a budget, a cap, or a patience limit — but a constant that claims
what content *is* has no disclosure that fixes it; it is rejected
outright, not shipped with a caveat.

## Real example this rule exists to prevent recurring

In one session, a fix for extracting a referenced element's label/number was
proposed **three separate times**, each time as a fixed text pattern:
first matching a specific ingestion metadata tag, then — once that tag
was found unreliable — matching the document's specific visible-label
format (all-caps, colon-separated) as the "safer"
replacement. Both were the same mistake at different levels of
specificity: neither would survive a different document's labeling
convention or language. The corrected fix used an LLM call to read the
real label in whatever form it takes, reusing an already-existing
upstream model call at zero new cost — the same reasoning the project
had *already* applied once for a structurally identical
problem, and then failed to apply consistently three sections later in
the same document.

A related, narrower instance of this same mistake: hardcoding a
specific structural pattern's name (e.g., "heading", "table") directly
into prompt instruction text, instead of teaching the general concept
the pattern is one example of. See
`.agents/rules/no-hardcoded-pattern-names-in-prompts.md` for that
narrower case — this rule is the general form of it, extended past
prompt wording to any fix: parsing logic, detection rules, thresholds,
regexes.

## How to apply

- Applies to every fix for a confirmed bug or gap — prompts, ingestion
  parsing, detection logic, thresholds, regexes — not only prompt text.
- When a real, confirmed problem is found against one project's data,
  explicitly check whether the *cause* is general (true of the product's
  whole intended scope) or genuinely specific to this one case before
  choosing how general the fix needs to be.
- If a fix is grounded in "this pattern works for the data I've tested,"
  say so explicitly and flag it as unverified for the general case —
  see `MEMORIES.md`'s rule against presenting untested rules as
  reliable — rather than silently shipping a narrow fix as if it were
  the general one. This covers a constant encoding a resource decision
  (a budget, a cap, a patience limit); it does not cover a constant
  that claims what content *is* — that kind is rejected outright, per
  "What a constant may encode" above, disclosure or not.
- When in doubt, prefer a mechanism that reasons about the underlying
  concept (an LLM judgment call, reusing an existing call site where
  possible) over a mechanism that matches the current example's literal
  shape.
