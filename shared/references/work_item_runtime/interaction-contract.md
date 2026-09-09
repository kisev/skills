# Shared Interaction Contract

Use `resolve -> prepare -> present -> confirm -> apply -> report`. Read-only
workflows end at `prepare -> present -> report`; prompt-only workflows need no
runner. Ask a **Question** only before `prepare`, and request **Confirmation**
only after `prepare` for an exact local mutation.

Evidence is complete only when every required input and check for the declared
scope was observed. Do not declare a result complete when evidence is partial,
stale, unknown, or contradictory. Return `partial`, `blocked`, or `error` with
structured missing evidence and a safe next step instead of guessing.

The preview contains TLDR, scope, risks, checks, artifact path, and SHA-256
digest. A confirmable CLI also shows TTL and an apply command with its digest.
Reject missing, changed, stale, expired, or used plans before writing. Every
durable state has one explicit owner. Manual-plan preparation does not publish
or change external state; stop after `report`.
