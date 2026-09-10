# Agent `review`

## Purpose

Review a bounded change and return a structured report.

## Triggers and Near-Misses

Use for review; near-miss: implementation.

## Inputs/Outputs

Input is exact diff and requirements; output is findings/report.

## Workflow Stages

Resolve diff, inspect contracts, test, classify findings, report.

## Dependencies

Repository evidence and routing receipt.

## Remote/Local Effects

Read-only.

## Errors/Partial/Escalation

Missing exact diff prevents a complete verdict.

## Unique Constraints

Findings are evidence-first and ranked.

## Requirement

### REQ-F-305 - Produce structured review reports

The review agent shall return findings bound to the exact current change.

## Example

`review` reports a regression with path, selector, and consequence.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
