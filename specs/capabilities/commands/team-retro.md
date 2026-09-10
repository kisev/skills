# `/team-retro`

## Purpose

Expose one fixed retrospective action.

## Triggers and Near-Misses

Routes retrospective context; near-miss: roadmap planning.

## Inputs/Outputs

Arguments select context/action; output is structured material.

## Workflow Stages

Select, pass, inspect, execute, validate, report.

## Dependencies

`team-retro` shared runtime.

## Remote/Local Effects

Declared local effects only.

## Errors/Partial/Escalation

Invalid action is structured failure.

## Unique Constraints

One fixed action per invocation.

## Requirement

### REQ-I-226 - Route the team-retro command

The command shall load exactly `team-retro` and preserve fixed-action selection.

## Example

`/team-retro` runs the selected retrospective action.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
