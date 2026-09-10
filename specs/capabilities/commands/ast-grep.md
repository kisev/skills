# `/ast-grep`

## Purpose

Expose the `ast-grep` skill as a thin command adapter.

## Triggers and Near-Misses

Routes syntax search/rewrite; near-miss: text substitution.

## Inputs/Outputs

Untrusted pattern arguments become skill input; output is search or plan.

## Workflow Stages

Select, pass, preview/apply through skill, report.

## Dependencies

`ast-grep` and native Skill loading.

## Remote/Local Effects

Effects match the skill and require its confirmation boundary.

## Errors/Partial/Escalation

Unsafe paths and stale plans escalate.

## Unique Constraints

No command argument bypasses rewrite safety.

## Requirement

### REQ-I-203 - Route the ast-grep command

The command shall load exactly `ast-grep` and preserve preview and digest checks.

## Example

`/ast-grep` passes a structural search pattern to the skill.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
