# `/code-explain`

## Purpose

Expose the `code-explain` skill as a thin command adapter.

## Triggers and Near-Misses

Routes bounded explanation; near-miss: code implementation.

## Inputs/Outputs

Untrusted range arguments become skill input; output is evidence-linked prose.

## Workflow Stages

Select, pass, explain, report.

## Dependencies

`code-explain` and native Skill loading.

## Remote/Local Effects

Local reads inherited from the skill.

## Errors/Partial/Escalation

Missing range or unreadable file remains partial.

## Unique Constraints

The command preserves revision and coverage bounds.

## Requirement

### REQ-I-204 - Route the code-explain command

The command shall load exactly `code-explain` and preserve its evidence boundary.

## Example

`/code-explain` routes a current diff range.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
