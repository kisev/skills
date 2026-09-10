# `/code-review`

## Purpose

Expose the `code-review` skill as a thin command adapter.

## Triggers and Near-Misses

Routes exact code review; near-miss: MR preparation.

## Inputs/Outputs

Untrusted scope arguments become review input; output is ranked findings.

## Workflow Stages

Select, pass, review, critic-check, report.

## Dependencies

`code-review` and native Skill loading.

## Remote/Local Effects

Read-only effects inherited from the skill.

## Errors/Partial/Escalation

Missing exact head or critic evidence blocks verdict.

## Unique Constraints

Command cannot turn review into mutation.

## Requirement

### REQ-I-205 - Route the code-review command

The command shall load exactly `code-review` and preserve independent evidence checks.

## Example

`/code-review` routes a local WIP to the review skill.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
