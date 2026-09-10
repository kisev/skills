# `task-review`

## Purpose

Review GitLab task or MR metadata and service fields without changing them.

## Triggers and Near-Misses

Trigger for metadata review; near-miss: implementation review or publication preparation.

## Inputs and Outputs

Input is an exact task or MR. Output is ranked metadata findings.

## Workflow Stages

Resolve object, collect fields and links, compare contracts, report.

## Dependencies

GitLab read access and exact object identity.

## Remote/Local Effects

Read-only remote and local evidence; no writes.

## Errors, Partial, Escalation

Unavailable fields or pagination are incomplete evidence.

## Unique Constraints

Review does not infer missing relationships or silently broaden scope.

## Requirement

### REQ-F-124 - Review metadata without mutation

The skill shall report exact task metadata findings without changing GitLab state.

## Example

`task-review` reports a missing label while preserving the task unchanged.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
