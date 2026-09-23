# One Value, One Owner

Recorded 2026-08-11 at the user's direction, after a review found one semantic
value in two writable stores.

## The rule

**A value with one meaning has exactly one owner.** Every other place that needs
it reads from that owner or derives from it. Two writable stores of one meaning
is a defect the moment it is written — not once they actually diverge.

Drift is silent by construction: both copies are individually valid, so nothing
inspecting either alone can catch it, and the failure surfaces far from its
cause, in whatever computed from the stale one.

## Violations

- One value on two objects, both writable, read by different consumers.
- A value written to a new location for one layer's convenience while the old
  one keeps its writers.
- A derived value cached beside its input with nothing forcing recomputation.
- Two defaults for one setting applied at different layers.

Not a violation: a **projection** — derived, written in one direction from one
owner, never independently written. If a reader must reason about which
location is fresher, it is not a projection.

## How to apply

Before adding any field or attribute carrying a value the system already holds:

1. Name the authoritative owner.
2. Search out every existing reader — do not assume the call sites you know are
   all of them — and confirm each reaches that owner.
3. If a second store is genuinely required, make it a projection.
4. If no single owner can be named, that is the design problem to solve first.
   Never proceed by adding the second store and planning to keep them in step.

When many call sites read the value, prefer one accessor over each site reaching
into the owner independently.

## Against the neighbouring rules

`architectural-reliability.md` §4/§6 ask a design to define its own source of
truth — satisfiable while still adding a second store for a value that already
had an owner elsewhere. `AGENTS.md` §14 is why duplication is repaired by
collapsing to one owner: synchronizing copies is the shim it prohibits.
