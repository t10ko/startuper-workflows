# UI and frontend analysis

This reference belongs to step 5a of the task-spec workflow — read it when the task has a UI or frontend surface.

## 5a. UI and frontend analysis — mandatory when the task has a UI or frontend surface

Do not consider UI coverage complete merely because the spec names a screen or component. Run `task-spec-contract-analyst` whenever the task adds, changes, exposes, or removes a UI or frontend surface, or a user-facing flow or text.

For every affected surface, cover:

- keyboard operability for every interactive element;
- focus management on open, close, navigation, and error states;
- screen-reader labeling for interactive elements, status changes, and dynamic content;
- color-contrast and motion requirements, including a reduced-motion path when animation communicates state;
- whether an existing component, template, or pattern already covers this need, checked against the project's own reuse registry or component convention when the project defines one, before assuming new construction is required;
- loading and skeleton states;
- optimistic update behavior and its rollback path on failure;
- in-progress or streaming states, checked against any progress or status transport contract the project already documents, so a new surface does not introduce a second, inconsistent mechanism;
- the substance and intent of user-facing text — what the user must understand and what action it should prompt — not its exact copy, which remains Level 4.

Treat accessibility gaps as `Blocker`, not `Polish`.

### UI readiness gate

UI coverage is complete only when:

- every affected surface has explicit keyboard, focus, screen-reader, and color-contrast/motion requirements;
- component and template reuse has been checked against the project's own convention before any new construction is assumed;
- loading, optimistic-update/rollback, and in-progress/streaming states are explicit and consistent with any existing progress/status transport contract;
- user-facing text substance and intent are defined for every state that affects understanding;
- acceptance criteria cover critical UI states and accessibility requirements;
- the UI specialist reports no unresolved blocker, or — when no UI specialist was dispatched — the coordinator has covered every item above itself and records in the document that it did.

Any missing item blocks `Requirements ready`.

