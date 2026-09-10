# `/skill-improve`

## Purpose

Expose skill contract improvement.

## Triggers and Near-Misses

Routes one skill check; near-miss: runtime code change.

## Inputs/Outputs

Arguments identify a skill; output is checked improvement.

## Workflow Stages

Select, pass, inspect, preview, apply, recheck, report.

## Dependencies

`skill-improve` validators.

## Remote/Local Effects

Confirmed local skill writes.

## Errors/Partial/Escalation

Validator failure remains explicit.

## Unique Constraints

Portability and locale boundaries remain intact.

## Requirement

### REQ-I-218 - Route the skill-improve command

The command shall load exactly `skill-improve` and preserve its validators.

## Example

`/skill-improve` checks one canonical skill.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
