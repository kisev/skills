# `/mr-prepare`

## Purpose

Expose exact merge-request preparation.

## Triggers and Near-Misses

Routes one MR URL; near-miss: issue preparation.

## Inputs/Outputs

Arguments identify one MR; output is a plan.

## Workflow Stages

Select, pass, collect, draft, finalize, report.

## Dependencies

`mr-prepare` and exact GitLab reads.

## Remote/Local Effects

Read-only external effects and local artifact.

## Errors/Partial/Escalation

Stale or incomplete CI blocks finalization.

## Unique Constraints

No publication.

## Requirement

### REQ-I-214 - Route the mr-prepare command

The command shall load exactly `mr-prepare` and never publish the MR.

## Example

`/mr-prepare` creates a local publication plan.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
