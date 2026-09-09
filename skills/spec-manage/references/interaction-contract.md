# Shared Interaction Contract

All workflows use `resolve -> prepare -> present -> confirm ->
apply -> report`. Omit only stages that do not apply: read-only workflows end at
`prepare -> present -> report` without `confirm` or `apply`; prompt-only
workflows follow the same visible protocol and need no runner.

## Question and Confirmation

Ask a **Question** only before `prepare` when a person must decide target,
scope, outcome, or acceptable risk. A broad GitLab target requires an exact
boundary before any listing or API request; it is not Confirmation.

Request **Confirmation** only after `prepare` for an exact local or external
mutation. A private preview artifact is not a mutation. Read-only collection,
review, and manual-plan preparation do not change external state.

## Present and Apply

The human preview contains TLDR, scope, risks, checks, the write-once artifact
path and its SHA-256 digest. Show conflicts completely. A confirmable CLI also
shows TTL and an apply command with its digest.

Executable apply rejects a missing, changed, stale, expired, or used plan before
writing. Report results and checks separately. JSON runners return a compact
summary, artifact/report path, SHA-256 digest, JSON errors and a non-zero exit
code.

## Boundaries

Do not publish or change external state in GitLab prepare/review workflows. Do
not change user-owned configuration without Confirmation. Stop after `report`.
