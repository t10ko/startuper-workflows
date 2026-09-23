# Failure-class analysis

This reference belongs to step 5b of the task-spec workflow — read it when the task under specification is a defect.

## 5b. Failure-class analysis — mandatory when the task is a defect

A reported defect is one visible symptom. Before the specification fixes its scope, establish whether the same contract is broken elsewhere. Run `task-spec-discovery-scout` whenever the task is a defect — a bug, error, regression, or behavior that already ships and is wrong. A new capability that has never worked is not a defect.

This analysis belongs here, not in implementation planning, for two reasons that are not interchangeable:

- **Sibling instances are scope.** Every confirmed sibling instance is a scope decision, and scope is settled with the user while the specification is open — not absorbed into a plan the user approved on a narrower reading.
- **The count can change the fix itself.** One broken call site is a local repair. The same contract broken across many is evidence that the shared-owner fix is an engineering design decision, recorded as a `DD` under §15, rather than N repetitions of one patch. Discovering this after the specification froze the fix framing means the framing was already wrong when it was approved.

On a defect task this specialist takes one of the discovery checkpoint's concurrent slots. When more specialists trigger than the checkpoint launches at once, it goes in the first batch — every later decision depends on whether the defect is one instance or a class.

Establish:

- the abstract broken contract, named as a concept rather than as the reported example's literal shape;
- the component that owns that contract today;
- every confirmed sibling instance, with path, symbol, and the evidence that the contract is broken there;
- near misses — structurally similar sites where the contract holds — with the evidence that it holds;
- contradictory handling of the same condition, where one call site treats as recoverable what another treats as an error, which `.agents/rules/no-unjustified-fallbacks.md` requires be resolved rather than left standing;
- whether the confirmed count implies `LOCAL` or `SHARED_OWNER_CANDIDATE` as the fix mechanism;
- the surfaces the sweep did not reach.

### Recording the result

Record each confirmed sibling under **In scope** or **Out of scope** in §2, with its rationale — never silently, and never only in prose. A deferred sibling is a decision the user made, so it belongs in §20 with the reason it was deferred.

Every sibling accepted into scope needs its own acceptance criterion in §16 and its own traceability row in §17. A sibling that ships with no criterion naming it is indistinguishable from one that was forgotten.

`detailed-plan` verifies this list rather than rebuilding it. A sibling that surfaces during planning and is absent here is a gap in this specification, and returns as a new question rather than being added downstream.

### Failure-class readiness gate

Failure-class coverage is complete only when:

- the abstract broken contract is named at the concept level, not as the reported example's shape;
- every confirmed sibling has an explicit in-scope or out-of-scope decision the user made;
- the fix mechanism is recorded as `LOCAL` or `SHARED_OWNER_CANDIDATE`, and a `SHARED_OWNER_CANDIDATE` has a corresponding `DD` in §15;
- every in-scope sibling has acceptance coverage;
- contradictory handling of the same condition is resolved rather than carried forward;
- the sweep's unreached surfaces are recorded as residual uncertainty rather than left implied;
- the failure-class specialist reports no unresolved blocker, or — when no failure-class specialist was dispatched — the coordinator has covered every item above itself and records in the document that it did.

Any missing item blocks `Requirements ready`.

