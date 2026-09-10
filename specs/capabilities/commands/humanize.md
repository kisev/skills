# `/humanize`

## Purpose

Expose the `humanize` prose-editing command.

## Triggers and Near-Misses

Routes Russian prose editing; near-miss: translation.

## Inputs/Outputs

Arguments are prose; output preserves protected tokens.

## Workflow Stages

Select, pass, edit, compare tokens, report.

## Dependencies

`humanize` and native Skill loading.

## Remote/Local Effects

Text-local only.

## Errors/Partial/Escalation

Protected-token conflicts escalate.

## Unique Constraints

No code or command changes.

## Requirement

### REQ-I-211 - Route the humanize command

The command shall load exactly `humanize` and preserve exact technical tokens.

## Example

`/humanize` edits a prose paragraph without changing an ID.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
