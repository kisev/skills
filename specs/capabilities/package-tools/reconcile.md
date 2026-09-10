# Package Tool `reconcile`

## Purpose

Preview or archive exact-owned retired public assets.

## Triggers and Near-Misses

Trigger for managed asset reconciliation; near-miss: arbitrary cleanup.

## Inputs/Outputs

Input is phase, scope, and digest; output is plan or archival result.

## Workflow Stages

Resolve scope, compare semantic ownership, preview, confirm, archive, verify, report.

## Dependencies

Lifecycle manifest, digest archive, and local state boundaries.

## Remote/Local Effects

Bounded local archive writes; no remote effects.

## Errors/Partial/Escalation

Stale, tampered, expired, or replayed receipts fail before writing.

## Unique Constraints

Historical goal/multi-run state and unknown/user-owned files remain unchanged.

## Requirement

### REQ-F-505 - Archive exact-owned retired assets

The tool shall archive only exact-owned retired assets content-addressably and preserve unrelated state.

## Example

`reconcile` archives a retired plugin once and leaves historical state byte-for-byte unchanged.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
