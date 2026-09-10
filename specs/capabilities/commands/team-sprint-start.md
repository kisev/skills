# `/team-sprint-start`

## Purpose

Expose one fixed sprint-start action.

## Triggers and Near-Misses

Routes sprint start; near-miss: sprint close.

## Inputs/Outputs

Arguments select context/action; output is validated start status.

## Workflow Stages

Select, pass, inspect prerequisites, execute, report.

## Dependencies

`team-sprint-start` shared runtime.

## Remote/Local Effects

Declared local state effects.

## Errors/Partial/Escalation

Invalid prerequisites block.

## Unique Constraints

No replacement state is inferred.

## Requirement

### REQ-I-229 - Route the sprint-start command

The command shall load exactly `team-sprint-start` and preserve prerequisite checks.

## Example

`/team-sprint-start` reports missing context without writing a substitute.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
