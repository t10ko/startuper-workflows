# Data and persistence analysis

This reference belongs to step 5 of the task-spec workflow — read it when the task involves data that persists.

## 5. Data and persistence analysis — mandatory when data persists

Do not jump directly to tables or documents. First specify the data semantics that any valid design must preserve.

For every persisted concept, establish:

- what real-world or domain fact it represents;
- source of truth;
- stable identity and uniqueness scope;
- ownership and tenant boundary;
- one-to-one, one-to-many, or many-to-many cardinality;
- required versus optional values and the meaning of missing/null;
- mutability: replace, append, version, or immutable;
- whether history, audit, snapshots, or provenance are required;
- lifecycle states and legal transitions;
- creation, expiration, archival, deletion, cascading, restoration, and retention semantics;
- consistency and atomicity requirements across related changes;
- duplicate, retry, race, and stale-write behavior;
- required reads, searches, filters, sorting, aggregation, and reporting;
- expected order of magnitude for rows/items, write rate, read rate, payload size, and retention when these affect design;
- sensitive-data classification, encryption or redaction requirements, and access boundaries;
- behavior for existing data, backfill, mixed versions, and rollback.

### Decide whether physical storage belongs in the document

A physical/logical storage decision belongs under **Engineering design decisions** when at least one is true:

- credible alternatives produce different correctness or consistency behavior;
- the choice changes migration or compatibility risk;
- required access patterns or scale make one representation materially safer;
- security, retention, encryption, or audit requirements depend on it;
- existing project architecture imposes a non-obvious constraint;
- an implementer would otherwise have to make a hard-to-reverse choice with insufficient context.

Examples of appropriate design decisions:

- separate table versus embedded JSON;
- association table versus duplicated values;
- append-only history versus mutable current record;
- canonical record plus projection versus multiple sources of truth;
- transaction grouping and uniqueness constraints;
- index requirements derived from explicit access patterns.

Do not decide physical storage merely for completeness when alternatives are equivalent, local, and reversible. Mark those as **Implementation discretion**.

### Data readiness gate

Data coverage is complete only when:

- every persisted concept has explicit semantics;
- ownership, identity, cardinality, lifecycle, and retention are clear;
- consistency and failure-after-mutation outcomes are defined;
- required access patterns are documented;
- existing-data and migration implications are addressed when relevant;
- any material storage decision is either accepted or explicitly open;
- acceptance criteria cover critical data invariants;
- the data specialist reports no unresolved requirement or contract blocker, or — when no data specialist was dispatched — the coordinator has covered every item above itself and records in the document that it did.

Any missing item blocks `Requirements ready`.

