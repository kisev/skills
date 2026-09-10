# `/docs-prepare`

## Purpose

Expose the `docs-prepare` skill as a document command adapter.

## Triggers and Near-Misses

Routes user-facing docs; near-miss: canonical specs.

## Inputs/Outputs

Arguments become bounded doc input; output follows the skill.

## Workflow Stages

Select, pass, inspect, draft, confirm if needed, report.

## Dependencies

`docs-prepare` and native Skill loading.

## Remote/Local Effects

Confirmed local document writes only.

## Errors/Partial/Escalation

Unsupported claims and broken links escalate.

## Unique Constraints

The command does not edit `specs/`.

## Requirement

### REQ-I-207 - Route the docs-prepare command

The command shall load exactly `docs-prepare` and preserve its scope exclusion.

## Example

`/docs-prepare` routes a reference-document request.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
