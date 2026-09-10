# `doit`

## Purpose

Coordinate an engineering change with preview, bounded execution, and verification.

## Triggers and Near-Misses

Trigger for implementation or repair; near-miss: specification-only onboarding.

## Inputs and Outputs

Input is a concrete engineering goal. Output is a verified change and structured report.

## Workflow Stages

Resolve scope, prepare plan, present, confirm, delegate, verify, report.

## Dependencies

Repository tools, tests, and eligible orchestration agents.

## Remote/Local Effects

Confirmed local writes; external effects only when explicitly in scope.

## Errors, Partial, Escalation

Failed checks or missing evidence produce structured escalation.

## Unique Constraints

Portable coordinator behavior remains host-neutral; OpenCode routing is an adapter.

## Requirement

### REQ-F-109 - Coordinate bounded changes

The skill shall execute only the confirmed scope and verify it before reporting success.

## Example

`doit` dispatches a worker only after a confirmed execution card.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
