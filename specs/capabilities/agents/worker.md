# Agent `worker`

## Purpose

Implement a confirmed scoped change and verify it.

## Triggers and Near-Misses

Use for implementation; near-miss: unconfirmed refactoring.

## Inputs/Outputs

Input is an execution card and receipt; output is a structured worker report.

## Workflow Stages

Resolve card, edit bounded files, run checks, report result and evidence.

## Dependencies

Routing receipt, execution card, repository tools.

## Remote/Local Effects

Confirmed local writes and declared effects only.

## Errors/Partial/Escalation

Failed checks or scope drift stop and escalate.

## Unique Constraints

Worker dispatch requires a confirmed execution card.

## Requirement

### REQ-F-304 - Bind worker implementation

The worker shall write only the confirmed scope and return a versioned structured report.

## Example

`worker` refuses implementation dispatch without an execution card.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
