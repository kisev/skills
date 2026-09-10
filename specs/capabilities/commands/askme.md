# `/askme`

## Purpose

Expose the `askme` skill as a thin command adapter.

## Triggers and Near-Misses

Routes dependency-bounded questions; near-miss: fully specified work.

## Inputs/Outputs

Untrusted arguments become interview input; output is ordered questions.

## Workflow Stages

Select, pass, interview, report.

## Dependencies

`askme` and native Skill loading.

## Remote/Local Effects

Read-only effects inherited from the skill.

## Errors/Partial/Escalation

Missing skill or unknown prerequisite escalates.

## Unique Constraints

The command cannot bypass question ordering.

## Requirement

### REQ-I-202 - Route the askme command

The command shall load exactly `askme` and preserve its dependency boundary.

## Example

`/askme` starts the native interview.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
