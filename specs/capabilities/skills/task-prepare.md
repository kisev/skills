# `task-prepare`

## Purpose

Prepare one GitLab task title, description, and verified publication plan.

## Triggers and Near-Misses

Trigger for one exact task source; near-miss: MR or release preparation.

## Inputs and Outputs

Input is one explicit source. Output is Russian title/description and Markdown plan.

## Workflow Stages

Resolve source, inspect facts, draft, validate links/fields, finalize, report.

## Dependencies

Exact GitLab context and repository evidence.

## Remote/Local Effects

Read-only external collection and local artifact; no publication.

## Errors, Partial, Escalation

Missing source or conflicting metadata blocks finalization.

## Unique Constraints

No batch creation, label choice, assignment, or mutation occurs.

## Requirement

### REQ-F-123 - Prepare one task without publication

The skill shall accept one exact source and produce a plan without creating or editing a task.

## Example

`task-prepare` validates a single issue URL and leaves publication to a later action.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
