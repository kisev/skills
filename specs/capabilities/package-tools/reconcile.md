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

Lifecycle manifest, digest archive, and local state boundaries.

## Remote/Local Effects

Bounded local archive and cleanup writes for package-owned OpenCode assets.
Portable skill trees and installer lock files are outside this boundary.

## Errors/Partial/Escalation

Stale, tampered, expired, or replayed receipts fail before writing. External
failure or a failed postcondition rolls bounded local state back.

## Unique Constraints

Historical goal/multi-run state, portable skills, and unknown/user-owned files
remain unchanged.

## Requirement

### REQ-F-505 - Archive exact-owned retired assets

Status: withdrawn on 2026-09-16 because reconciliation is now CLI-only.

Former requirement: the tool shall archive exact-owned retired package assets
content-addressably, validate bounded postconditions, roll known planned paths
back on failure, and preserve unrelated state.

## Example

`reconcile` archives an exact-owned retired package command and leaves portable
skills unchanged.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
