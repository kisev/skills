# `mr-prepare`

## Purpose

Prepare one exact GitLab merge request title, description, and publication plan.

## Triggers and Near-Misses

Trigger for an exact MR URL; near-miss: issue preparation or code review.

## Inputs and Outputs

Input is one MR URL. Output is a fresh Markdown plan with evidence and digest.

## Workflow Stages

Resolve refs, collect paginated metadata, inspect diff/CI, draft, finalize, report.

## Dependencies

GitLab read access and local Git.

## Remote/Local Effects

Exact external GET reads and local private artifact; no publication.

## Errors, Partial, Escalation

Pagination or freshness failure blocks a complete plan.

## Unique Constraints

No label selection, channel choice, or external mutation is performed.

## Requirement

### REQ-F-114 - Prepare exact merge requests

The skill shall require one exact MR boundary and never publish or mutate GitLab.

## Example

`mr-prepare` refuses a broad project request before API collection.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
