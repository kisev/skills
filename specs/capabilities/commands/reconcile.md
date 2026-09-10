# `/reconcile`

## Purpose

Preview or apply scope-isolated reconciliation of retired managed assets.

## Triggers and Near-Misses

Trigger for exact-owned cleanup; near-miss: arbitrary file deletion.

## Inputs/Outputs

Input is phase, scope, and confirmation digest; output is plan or receipt.

## Workflow Stages

Resolve scope, preview ownership, present, confirm, archive, report.

## Dependencies

Core reconcile tool, semantic manifest, and archive.

## Remote/Local Effects

Bounded local mutation on confirmed apply; no remote effects.

## Errors/Partial/Escalation

Stale, tampered, expired, or replayed confirmations fail safely.

## Unique Constraints

Unknown sources, runtime state, and user-owned files are untouched.

## Requirement

### REQ-I-232 - Route the reconcile package command

The command shall invoke package tool `reconcile` and require a fresh confirmation digest for apply.

## Example

`/reconcile` previews retired assets before archiving them.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
