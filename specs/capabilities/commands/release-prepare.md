# `/release-prepare`

## Purpose

Expose release-plan preparation.

## Triggers and Near-Misses

Routes exact release MR; near-miss: release review.

## Inputs/Outputs

Arguments identify the boundary; output is stable target-scoped
`release-publication.md` with announcement material.

## Workflow Stages

Select, pass, inventory, draft, finalize, report.

## Dependencies

`release-prepare` and Git evidence.

## Remote/Local Effects

Read-only collection and atomic local plan replacement; no tag or publish.

## Errors/Partial/Escalation

Missing base/head or CI is blocking.

## Unique Constraints

Announcement sending is excluded.

## Requirement

### REQ-I-215 - Route the release-prepare command

The command shall load exactly `release-prepare`, report only its stable
user-facing plan path, and perform no release mutation.

## Example

`/release-prepare` prepares a release MR plan.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
