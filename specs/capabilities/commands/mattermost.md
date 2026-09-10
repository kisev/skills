# `/mattermost`

## Purpose

Expose bounded Mattermost reading.

## Triggers and Near-Misses

Routes exact Mattermost reads; near-miss: posting.

## Inputs/Outputs

Arguments are URL and bounded scope; output is redacted evidence.

## Workflow Stages

Select, pass, GET, normalize, report.

## Dependencies

`mattermost` and native Skill loading.

## Remote/Local Effects

GET-only external reads inherited from the skill.

## Errors/Partial/Escalation

Auth and pagination gaps remain explicit.

## Unique Constraints

No command-side posting.

## Requirement

### REQ-I-213 - Route the mattermost command

The command shall load exactly `mattermost` and preserve GET-only boundaries.

## Example

`/mattermost` reads a supplied thread URL.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
