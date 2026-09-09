# Shared Interaction Contract

All workflows use `resolve -> prepare -> present -> confirm ->
apply -> report`. Omit only stages that do not apply: read-only workflows end at
`prepare -> present -> report` without `confirm` or `apply`; prompt-only
workflows follow the same visible protocol and need no runner.

## Evidence and Results

Evidence is complete only when every required input, page, file, dependency, and
check for the declared scope was observed and bound to the relevant revision.
Do not declare a result complete when evidence is partial, stale, unknown, or
contradictory. Return `partial` when useful bounded results exist with gaps,
`blocked` when a required decision or dependency prevents safe continuation,
and `error` when the operation cannot produce a trustworthy result. Include
structured errors, missing evidence, consequence, and the safe escalation or
next step. Escalate instead of guessing, widening scope, or silently retrying a
different operation.

## Question and Confirmation

Ask a **Question** only before `prepare` when a person must decide target,
scope, outcome, or acceptable risk. First inspect facts that can be verified.
Ask independent decision questions in rounds; do not repeat answered questions
or ask a question whose prerequisites depend on another unanswered question. A
broad GitLab target requires an exact boundary before any listing or API request;
it is not Confirmation.

Request **Confirmation** only after `prepare` for an exact local or external
mutation. Group confirmations by independent risk, not by file. One approval may
cover only the actions already shown in the plan with the same mutation boundary.
External publication, history rewrite, and destructive cleanup always require
separate confirmations. A private preview artifact is not a mutation. Read-only
collection, review, and manual-plan preparation do not change external state.

## Present and Apply

The human preview contains TLDR, scope, risks, checks, the write-once artifact
path and its SHA-256 digest. Show conflicts completely. A confirmable CLI also
shows TTL and an apply command with its digest.

Executable apply rejects a missing, changed, stale, expired, or used plan before
writing. Report status, results, evidence completeness, errors, and checks
separately. JSON runners return a compact summary, artifact/report path,
SHA-256 digest, structured errors, and a non-zero exit code for failure.

## Boundaries

Every durable state has one explicit owner. A portable skill may read or update
its declared state only; it must not create a hidden shared lifecycle, infer
ownership from a caller, or mutate another workflow's state. Do not publish or
change external state in GitLab prepare/review workflows. Do not change
user-owned configuration without Confirmation. Stop after `report`.
