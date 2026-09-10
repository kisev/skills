# `/docs-review`

## Purpose

Expose the `docs-review` skill as a read-only command adapter.

## Triggers and Near-Misses

Routes user-facing documentation review; near-miss: canonical spec audit.

## Inputs/Outputs

Arguments become review scope; output is findings.

## Workflow Stages

Select, pass, inspect sources, report.

## Dependencies

`docs-review` and native Skill loading.

## Remote/Local Effects

Read-only local effects.

## Errors/Partial/Escalation

Spec paths redirect to `spec-manage`.

## Unique Constraints

No command-side edits.

## Requirement

### REQ-I-208 - Route the docs-review command

The command shall load exactly `docs-review` and preserve read-only behavior.

## Example

`/docs-review` reports a broken documentation link.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
