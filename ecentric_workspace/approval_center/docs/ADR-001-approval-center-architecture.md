# ADR-001: Approval Center application architecture

- Status: Accepted
- Date: 2026-08-18
- Scope: `ecentric_workspace.approval_center`

## Implementation status

Implemented on 2026-08-18:

- all 26 business request types have immutable registered definitions;
- all business modules live below `features/<request_type>` instead of being exposed
  as top-level packages;
- every feature separates immutable domain configuration, application orchestration,
  API controllers, UI assets, and Frappe infrastructure;
- public `api/*.py` files are compatibility wrappers for unchanged Frappe dotted paths;
- APIs delegate through the immutable singleton `shared.facade.APPROVAL_FACADE`;
- fulfillment request types share one fulfillment application service;
- specialized AI Topup behavior lives under `features/ai_topup` behind its unchanged
  public API path;
- the authoritative engine implementation lives under `shared/workflow`; the legacy
  `engine`, `request_types`, and `services` compatibility packages have been removed;
- e-sign platform ownership remains complete under `platform/esign`;
- no Web Page HTML or drift-lock source is changed by this migration.
- orphaned compatibility packages `core/` and `application/` have been removed;
  their authoritative implementations already live in the shared and business modules.

## Context

Approval Center already has a generic workflow engine. `shared/workflow/transitions.py` owns the
authoritative write-side transitions for all approval business DocTypes through
`business_doctype`: submit, approve, reject, request information, resubmit, cancel,
fulfillment transitions, and admin override. The other `shared/workflow/` modules
separate permissions, user rules, participant rules, and business-hour/SLA concerns.

The principal duplication is not the transition engine. It is the read/application
layer in `api/*.py`: requester context, visibility, capabilities, list queries,
detail projection, and thin orchestration are repeated for each request type.

Frappe conventions remain hard boundaries. DocType controllers and JSON stay under
`approval_center/doctype`, Frappe Pages stay under `approval_center/page`, public
assets stay under the app's `public` pipeline, and deployed patch dotted paths are
never moved or renamed.

## Feature package layout

```text
approval_center/
  api/                         # stable public dotted-path adapters
  features/
    <request_type>/
      domain/definition.py     # immutable request contract/configuration
      application/service.py   # request-specific use cases
      controllers/api.py       # transport adapter
      ui/main_section.html     # page asset
      infrastructure/          # setup, activation, page synchronization
  shared/                      # request-agnostic abstractions and workflow core
  doctype/, page/, patches/    # Frappe-owned layout; intentionally unchanged
```

Only package markers (`__init__.py`) may sit at a feature root. Compatibility files
at the Approval Center root and under `api/` are explicit framework/public-boundary
exceptions; they contain no business logic.

## Decision

### 1. Refactor the existing engine; do not build a second engine

The transition service is split into cohesive modules while preserving its behavior and
compatibility imports, into cohesive workflow modules such as:

```text
approval_center/shared/workflow/
  process.py
  participants.py
  transitions.py
  permissions.py
```

Focused permissions, user rules, calendars, and participant modules live directly
under `shared/workflow`; there is one authoritative write-side state machine.

### 2. Add the missing generic request application layer

The new shared layer is:

```text
approval_center/shared/requests/
  query_service.py
  command_service.py
  capabilities.py
  contracts.py
```

- `query_service.py` owns permission-safe list/detail projections.
- `capabilities.py` derives UI capabilities from authoritative server-side rules.
- `command_service.py` performs common orchestration and delegates transitions to
  the existing workflow engine. It does not implement a second state machine.
- `contracts.py` defines the immutable request-type contract.

Whitelisted API modules remain transport adapters. They parse inputs, call the
application layer, and return stable payloads. Business mutations do not live in
API modules.

### 3. Use one explicit request-type registry

The composition root will be:

```text
approval_center/shared/registry.py
```

It owns the explicit mapping:

```python
APPROVAL_DEFINITIONS = {
    "LEAVE_REQUEST": LEAVE_DEFINITION,
    "PAYMENT_REQUEST": PAYMENT_REQUEST_DEFINITION,
}
```

Core modules depend on the request-definition contract and registry lookup, never
on a feature module chosen through conditional imports. Feature modules may depend
on core. The registry is the only place allowed to know every concrete request-type
module.

A central Python registry is preferred over a custom `hooks.py` hook for now because
request types are owned by this app and require deterministic startup validation.
If third-party apps must contribute request types later, this decision can be
superseded by a hook-based extension mechanism.

Registry validation must fail fast in tests for:

- duplicate approval codes;
- a definition whose declared code differs from its registry key;
- mutable or stateful definitions;
- missing required contract members;
- duplicate business DocType ownership, unless explicitly supported.

No implicit module scanning or naming-convention discovery is permitted.

### 4. Request definitions are immutable stateless singletons

Each registered definition is created once and reused. It contains configuration
and pure behavior only. It must not retain request-, user-, site-, or transaction-
specific state.

Implementation constraints:

- use an immutable representation such as `@dataclass(frozen=True, slots=True)`;
- use tuples/frozen values instead of mutable lists, sets, or dictionaries;
- pass `doc`, actor, and request context explicitly to every operation;
- never cache a Frappe Document, current user, request context, or computed result on
  `self`;
- never mutate a definition after registration.

These constraints prevent cross-request and cross-user data leakage in long-lived
Frappe web and worker processes.

### 5. Preserve every public API path during internal refactoring

Database-backed Web Page HTML is protected by SHA-256 drift locks. Internal Python
refactoring must not require changing that HTML.

Existing dotted paths and whitelisted function names therefore remain stable, for
example:

```text
ecentric_workspace.approval_center.api.leave.submit_request
```

Legacy API modules become compatibility wrappers around the new application layer.
Function names, HTTP method constraints, arguments, and response contracts must not
change during this refactor. Contract tests will lock these surfaces.

### 6. E-sign platform ownership is complete

**DONE:** the e-sign implementation has been moved to
`ecentric_workspace.platform.esign`; the drift lock has been bumped and verification
completed. Approval Center integrates with that platform capability and does not
create another e-sign implementation.

Any Frappe metadata that physically remains under the Approval Center module for
framework/module compatibility does not transfer runtime service ownership back to
Approval Center.

## Dependency direction

```text
Web Page / public API compatibility wrapper
                 |
                 v
       business module API/service
                 |
                 v
       shared singleton facade
          |                    |
          v                    v
module-owned definition   shared/workflow
          |                    |
          +---------> Frappe DocTypes

Approval Center ----integration port----> platform/esign
```

The workflow core must not import individual request types. Reporting is read-only
with respect to workflow transitions.

## Migration sequence

1. Add contracts, the explicit registry, and registry contract tests.
2. Extract shared query and capability behavior from `api/*.py` without changing
   endpoint paths or payloads.
3. Migrate one representative request type (Leave) behind its existing API module.
4. Compare old/new behavior with API contract and permission regression tests.
5. Migrate the remaining request types in bounded waves.
6. Move all consumers to `shared/workflow` and remove compatibility imports.
7. Remove duplicated private API helpers only after all consumers use the shared
   application layer.

The registry is established before the first feature migration. The engine split is
not a prerequisite for eliminating read-side duplication.

## Non-goals

- Rewriting the approval workflow engine.
- Moving Frappe DocTypes outside their module directory.
- Renaming deployed patches.
- Changing Web Page HTML or its drift locks as part of the Python refactor.
- Changing existing whitelisted API paths or response contracts.
- Introducing dynamic request-type plugins before there is a cross-app consumer.

## Consequences

- One workflow state machine remains authoritative.
- Shared list/detail/capability fixes apply consistently to all request types.
- Adding a request type requires an explicit, reviewable registry entry.
- Stateless definitions are safe to reuse across Frappe workers and web requests.
- Existing database-backed pages remain untouched during the refactor.
- Compatibility wrappers add temporary indirection, which can remain permanently if
  the public dotted paths are treated as stable API.
