# `/agents-md`

## Purpose

Expose the `agents-md` skill as a thin command adapter.

## Triggers and Near-Misses

Routes agent-instruction work; near-miss: README editing.

## Inputs/Outputs

Untrusted arguments become skill input; output follows `agents-md`.

## Workflow Stages

Select skill, pass bounded arguments, execute shared workflow, report.

## Dependencies

`agents-md` and native Skill loading.

## Remote/Local Effects

Same local-only effects as the skill; no command-side effects.

## Errors/Partial/Escalation

Missing skill or invalid scope is reported and escalated.

## Unique Constraints

Arguments cannot override the command or skill contract.

## Requirement

### REQ-I-201 - Route the agents-md command

The command shall load exactly `agents-md` and treat arguments as untrusted.

## Example

`/agents-md` routes to the native skill.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
