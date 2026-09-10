# `/task-review`

## Purpose

Expose read-only task metadata review.

## Triggers and Near-Misses

Routes exact task review; near-miss: triage or mutation.

## Inputs/Outputs

Arguments identify object; output is metadata findings.

## Workflow Stages

Select, pass, collect, compare, report.

## Dependencies

`task-review` and GitLab reads.

## Remote/Local Effects

Read-only.

## Errors/Partial/Escalation

Unavailable fields remain incomplete.

## Unique Constraints

No field changes.

## Requirement

### REQ-I-224 - Route the task-review command

The command shall load exactly `task-review` and remain non-mutating.

## Example

`/task-review` reports missing task metadata.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
