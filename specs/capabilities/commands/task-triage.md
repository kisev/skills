# `/task-triage`

## Purpose

Expose evidence-bounded task triage.

## Triggers and Near-Misses

Routes substantive triage; near-miss: publication.

## Inputs/Outputs

Arguments identify task scope; output separates facts and recommendations.

## Workflow Stages

Select, pass, collect, classify, recommend, report.

## Dependencies

`task-triage` and exact GitLab scope.

## Remote/Local Effects

Read-only.

## Errors/Partial/Escalation

Partial collection is explicit.

## Unique Constraints

Recommendations are not automatic decisions.

## Requirement

### REQ-I-225 - Route the task-triage command

The command shall load exactly `task-triage` and preserve evidence classification.

## Example

`/task-triage` analyzes an explicitly supplied issue set.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
