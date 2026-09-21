# Agent `critic`

## Purpose

Independently challenge a review or implementation conclusion.

## Triggers and Near-Misses

Use for independent critique; near-miss: duplicating the primary review.

## Inputs/Outputs

Input is the exact scope and bounded evidence snapshot without the primary
reviewer's conclusions. Output is independent candidate findings or an explicit
no-findings result.

## Workflow Stages

Resolve independent boundary, inspect, challenge, classify, report.

## Dependencies

Exact diff, requirements, and separate routing receipt.

## Remote/Local Effects

Read-only.

## Errors/Partial/Escalation

Missing independence, exposure to primary conclusions, or evidence that differs
from the primary snapshot invalidates the critique. A required audit then
continues as partial rather than substituting a repeated primary pass.

## Unique Constraints

Critic cannot approve based solely on the primary report.

## Requirement

### REQ-F-306 - Preserve independent criticism

The critic shall independently evaluate the exact scope against the same bounded
evidence snapshot, without receiving primary conclusions, and shall return its
own candidate findings or an explicit no-findings result. The primary reviewer
shall disposition every candidate as accepted, rejected, or duplicate with an
evidence-based reason.

## Example

`critic` rejects a review conclusion unsupported by a current test.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
