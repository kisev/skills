# `/release-review`

## Purpose

Expose exact release readiness review.

## Triggers and Near-Misses

Routes release review; near-miss: release publication.

## Inputs/Outputs

Arguments identify one release MR; output is findings/status.

## Workflow Stages

Select, pass, inspect, classify, report.

## Dependencies

`release-review` and fresh CI evidence.

## Remote/Local Effects

Read-only effects.

## Errors/Partial/Escalation

Missing freshness blocks readiness.

## Unique Constraints

No version or tag mutation.

## Requirement

### REQ-I-216 - Route the release-review command

The command shall load exactly `release-review` and preserve read-only verdicts.

## Example

`/release-review` reports a stale pipeline as not ready.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
