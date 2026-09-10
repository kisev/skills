# `/task-prepare`

## Purpose

Expose one-task GitLab preparation.

## Triggers and Near-Misses

Routes one exact task source; near-miss: MR preparation.

## Inputs/Outputs

Arguments identify one source; output is a plan.

## Workflow Stages

Select, pass, collect, draft, validate, report.

## Dependencies

`task-prepare` and exact source evidence.

## Remote/Local Effects

Read-only remote and local artifact.

## Errors/Partial/Escalation

Conflicting metadata blocks finalization.

## Unique Constraints

No publication.

## Requirement

### REQ-I-223 - Route the task-prepare command

The command shall load exactly `task-prepare` without creating a task.

## Example

`/task-prepare` prepares one issue plan.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
