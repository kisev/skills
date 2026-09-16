# Package Tool `reconcile`

- Status: withdrawn
- Status changed: 2026-09-16
- Reason: Reconciliation remains available through `skills-opencode reconcile`.

## Purpose

Historical capability record for the retired OpenCode package tool.

## Triggers and Near-Misses

Trigger for managed asset reconciliation; near-miss: arbitrary cleanup.

## Inputs/Outputs

Input is phase, optional scope defaulting to project, and digest; output is a
plan or archival/removal result.

## Workflow Stages

Resolve scope, compare semantic ownership, preview, confirm, archive, verify, report.

## Dependencies

Lifecycle manifest, portable source marker, configured exact `skills` CLI,
digest archive, and local state boundaries.

## Remote/Local Effects

Bounded local archive and cleanup writes. Confirmed portable cleanup may resolve
the configured pinned CLI through `npx`; npm cache and network effects are outside
the rollback boundary.

## Errors/Partial/Escalation

Stale, tampered, expired, or replayed receipts fail before writing. External
failure or a failed postcondition rolls bounded local state back.

## Unique Constraints

Historical goal/multi-run state, pre-marker skills, and unknown/user-owned files
remain unchanged.

## Requirement

### REQ-F-505 - Archive exact-owned retired assets

Status: withdrawn on 2026-09-16 because reconciliation is now CLI-only.

Former requirement: the tool shall archive exact-owned retired assets content-addressably, invoke the
configured exact `skills` CLI directly for marked portable cleanup, validate
bounded postconditions, roll known planned paths back on failure, and preserve
unrelated state on a best-effort basis under concurrent external changes.

## Example

`reconcile` archives a marked renamed skill, removes it through `skills`, and
leaves an unmarked external skill unchanged.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
