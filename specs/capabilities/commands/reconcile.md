# `/reconcile`

- Status: withdrawn
- Status changed: 2026-09-16
- Reason: Reconciliation remains available through `skills-opencode reconcile`.

## Purpose

Historical capability record for the retired slash-command adapter.

## Triggers and Near-Misses

Trigger for exact-owned cleanup; near-miss: arbitrary file deletion.

## Inputs/Outputs

Input is phase, optional scope defaulting to project, and confirmation digest;
output is a plan or receipt.

## Workflow Stages

Resolve scope, preview ownership, present, confirm, archive, report.

## Dependencies

Core reconcile tool, semantic manifest, and archive.

## Remote/Local Effects

Bounded local mutation on confirmed apply; marked portable cleanup invokes the
configured exact external `skills` CLI for OpenCode and Codex.

## Errors/Partial/Escalation

Stale, tampered, expired, or replayed confirmations fail safely.

## Unique Constraints

Unknown or pre-marker sources, runtime state, and user-owned files are untouched.

## Requirement

### REQ-I-232 - Route the reconcile package command

Status: withdrawn on 2026-09-16 because reconciliation is now CLI-only.

Former requirement: the command shall expose the exact package-tool argument schema, default omitted
scope to project, invoke package tool `reconcile`, and require a fresh
confirmation digest for apply.

## Example

`/reconcile` previews retired assets before archiving them.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
