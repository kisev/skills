# `/team-sprint-close`

## Purpose

Expose one fixed sprint-close action.

## Triggers and Near-Misses

Routes sprint closure; near-miss: sprint start.

## Inputs/Outputs

Arguments select context/action; output is validated close status.

## Workflow Stages

Select, pass, inspect, execute, digest-check, report.

## Dependencies

`team-sprint-close` shared runtime.

## Remote/Local Effects

Declared local state effects.

## Errors/Partial/Escalation

Stale plans are rejected.

## Unique Constraints

Fresh evidence is required.

## Requirement

### REQ-I-228 - Route the sprint-close command

The command shall load exactly `team-sprint-close` and preserve digest validation.

## Example

`/team-sprint-close` rejects a replayed plan.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
