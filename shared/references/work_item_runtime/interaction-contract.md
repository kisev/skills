# Shared Interaction Contract

Use `resolve -> prepare -> present -> report` for chat output and `resolve ->
prepare -> apply -> report` for bounded project-file output. Ask a **Question**
only before `prepare`. Write an explicitly requested workspace-relative output
directly with atomic replacement; do not create a preview artifact or request
Confirmation.

Evidence is complete only when every required input and check for the declared
scope was observed. Do not declare a result complete when evidence is partial,
stale, unknown, or contradictory. Return `partial`, `blocked`, or `error` with
structured missing evidence and a safe next step instead of guessing.

Reject absolute, traversal, symlink, and unsafe-parent output paths before
writing. Every durable state has one explicit owner. Manual-plan preparation does
not publish or change external state; stop after `report`.
