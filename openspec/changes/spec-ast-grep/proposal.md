# Proposal

## Why

ast-grep — kept in the foundation renegotiation (see `renegotiate-foundation`) with its details deliberately deferred. This change gives the component its exhaustive
specification and executes the renegotiation decisions that concern it.

## What Changes

Wrapper over the external ast-grep CLI: structural search (read-only) and confirmed rewrites with all-files-prepared atomicity and rollback.

Known defect: confirmed broken in the authored tree — imports a module that exists only after build, and the requirements manifest is missing even from .build.
Open: repair-or-drop decision, exhaustive capability spec.

## Capabilities

### New Capabilities

None yet — the exhaustive capability spec for this component is drafted
inside this change when it is picked up.

### Modified Capabilities

None.

## Impact

`skills/ast-grep`; zero relations today.
