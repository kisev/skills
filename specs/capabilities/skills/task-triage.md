# `task-triage`

## Purpose

Analyze one or more explicit GitLab tasks with facts, assumptions, constraints, and recommendations.

## Triggers and Near-Misses

Trigger for substantive triage; near-miss: publishing a task or changing implementation.

## Inputs and Outputs

Input is an explicit task set and scope. Output is a read-only triage assessment.

## Workflow Stages

Resolve identity, collect bounded evidence, separate certainty, recommend, report.

## Dependencies

GitLab read access, repository evidence, and exact scope.

## Remote/Local Effects

Read-only external/local effects; no mutation.

## Errors, Partial, Escalation

Partial collection remains partial and identifies affected conclusions.

## Unique Constraints

Recommendations do not become decisions or implementation plans automatically.

## Requirement

### REQ-F-125 - Keep triage evidence-bounded

The skill shall separate confirmed facts from assumptions and recommendations in read-only output.

## Example

`task-triage` labels a missing acceptance criterion as unknown and recommends clarification.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
