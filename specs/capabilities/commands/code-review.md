# `/code-review`

## Purpose

Expose the `code-review` skill as a thin command adapter.

## Triggers and Near-Misses

Routes exact code review; near-miss: MR preparation.

## Inputs/Outputs

Untrusted scope arguments become review input; output is the skill's compact
assessment and publication-plan paths.

## Workflow Stages

Select, pass, review, critic-check, report.

## Dependencies

`code-review` and native Skill loading.

## Remote/Local Effects

The command adapter only loads the skill and has no direct effects. Review
preparation and any separately confirmed helper effects remain owned by the
portable skill.

## Errors/Partial/Escalation

Missing exact head or critic evidence blocks verdict.

## Unique Constraints

The command cannot implement or invoke publication, label analysis, confirmation
digests, helper actions, runner selection, or environment handling.

## Requirement

### REQ-I-205 - Route the code-review command

The command shall load exactly `code-review`, pass its arguments as untrusted
input, and contain no target parsing, remote/local selection, runner invocation,
state transition, publication-helper invocation, confirmation, label analysis,
environment handling, or review logic.

## Example

`/code-review` routes a local WIP to the review skill.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
