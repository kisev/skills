# `task-review`

## Purpose

Review one storage-neutral work item for quality without changing external state.

## Triggers and Near-Misses

Trigger for quality review of one task source; near-miss: code review, triage, or publication.

## Inputs and Outputs

Input is inline text, a local regular file, or an exact HTTPS link. Output is one `ready`, `needs_clarification`, or `blocked` verdict with evidence-backed findings and recommendations.

## Workflow Stages

Resolve and load one source, normalize to `work-item/v1`, separate machine and semantic findings, assess quality, present, report.

## Dependencies

One readable source, host HTTPS reading when selected, and the bundled work-item contract and validator.

## Remote/Local Effects

Chat output by default; optional file output only after exact preview and digest confirmation; no external mutation or publication.

## Errors, Partial, Escalation

A missing, multiple, non-regular, or unreadable source blocks review; unresolved quality conditions yield `needs_clarification` or `blocked`.

## Unique Constraints

The same normalized item and evidence produce the same verdict; tracker metadata is never invented.

## Requirement

### REQ-F-124 - Review one storage-neutral work item

The skill shall normalize exactly one supported source to `work-item/v1` and
return exactly one `ready`, `needs_clarification`, or `blocked` verdict with
machine and semantic findings kept distinct, without publication or external
mutation.

## Example

`task-review` marks a local work-item file `needs_clarification` when acceptance evidence is missing.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
