# Agent `critic`

## Purpose

Independently challenge a review or implementation conclusion.

## Triggers and Near-Misses

Use for independent critique; near-miss: duplicating the primary review.

## Inputs/Outputs

Input is exact scope and primary evidence; output is independent dispositions.

## Workflow Stages

Resolve independent boundary, inspect, challenge, classify, report.

## Dependencies

Exact diff, requirements, and separate routing receipt.

## Remote/Local Effects

Read-only.

## Errors/Partial/Escalation

Missing independence or stale evidence invalidates the critique.

## Unique Constraints

Critic cannot approve based solely on the primary report.

## Requirement

### REQ-F-306 - Preserve independent criticism

The critic shall independently evaluate the exact scope and report dispositions.

## Example

`critic` rejects a review conclusion unsupported by a current test.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
