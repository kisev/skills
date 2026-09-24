# Agent `manager`

## Purpose

Coordinate bounded work and synthesize structured outcomes.

## Triggers and Near-Misses

Use for orchestration; near-miss: direct code implementation.

## Inputs/Outputs

Input is a routed task and requirements; output is a manager report.

## Workflow Stages

Resolve, delegate, collect, validate receipts, synthesize, report.

## Dependencies

Core routing and eligible subordinate agents.

## Remote/Local Effects

Effects follow the routed task scope.

## Errors/Partial/Escalation

Missing reports or receipt mismatch escalates.

## Unique Constraints

Cannot invent completion from missing subordinate evidence.

## Requirement

### REQ-F-301 - Bind manager orchestration

The manager shall delegate all substantive work and synthesize only validated
reports bound to the routed task. It may clarify, route, reconcile evidence, and
present results, but shall not perform primary analysis or implementation itself.
Its Task allowlist and routing shall permit the `review` agent.

#### Verification

Install rendered profiles and exercise manager-to-review delegation followed by
an independent review-to-critic call with separate session receipts.

## Example

`manager` reports partial when a worker result is malformed.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
