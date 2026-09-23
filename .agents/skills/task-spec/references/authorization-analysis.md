# Authorization analysis

This reference belongs to step 4 of the task-spec workflow — read it when the task involves a resource that needs an authorization decision.

## 4. Authorization analysis — mandatory when a resource is involved

Do not consider permissions covered merely because the spec says “authorized users” or names one role.

Build the authorization model from:

`subject × identity type × action × resource × ownership × tenant × resource state × access path × agent/tool capability scope`

For every externally reachable operation, cover:

- authenticated versus anonymous;
- each relevant role;
- owner versus non-owner;
- same-tenant versus cross-tenant;
- active, suspended, revoked, deleted, expired, or archived identities/resources;
- direct access and indirect access through lists, search, exports, batch operations, background jobs, webhooks, admin tools, and related objects;
- read, create, update, delete, approve, retry, restore, export, and administrative variants when relevant;
- field-level visibility and mutation rights;
- for an autonomous agent or tool-using subject, the scope of tools and capabilities it may invoke on the user's behalf;
- whether denial reveals resource existence;
- whether validation, lookup, or other observable work may occur before authorization;
- audit expectations for allowed and denied sensitive actions;
- emergency, support, service-account, impersonation, and super-admin paths if they exist;
- agent-to-agent and agent-to-external-service trust, including whether one automated caller may act on another's credentials or authority without an explicit grant.

Use deny-by-default as an analysis posture unless repository policy explicitly says otherwise. Record the actual required policy rather than assuming one.

### Authorization readiness gate

Permissions are complete only when:

- every relevant operation appears in the permission matrix;
- every actor class has an explicit allow or deny outcome;
- ownership and tenant rules are explicit;
- state-dependent permission changes are explicit;
- indirect paths cannot bypass the policy;
- denial and information-disclosure behavior are defined;
- acceptance criteria cover critical allows and denies;
- the authz specialist reports no unresolved blocker, or — when no authz specialist was dispatched — the coordinator has covered every item above itself and records in the document that it did.

Any missing item blocks `Requirements ready`.

