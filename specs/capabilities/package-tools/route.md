# Package Tool `route`

## Purpose

Resolve a capability category and dispatch one eligible host agent.

## Triggers and Near-Misses

Trigger for bounded orchestration; near-miss: direct unbound Task calls.

## Inputs/Outputs

Input is action, category, task, requirements, card, and optional override; output is decision/receipt.

## Workflow Stages

Resolve host inventory, preview/dispatch, grant receipt, consume once, complete report.

## Dependencies

OpenCode host agents, `RoutingGate`, execution-card schemas.

## Remote/Local Effects

Host-local routing and delegated task effects; no implicit remote effects.

## Errors/Partial/Escalation

Unknown agents, missing card, stale receipt, or malformed report fails safely.

## Unique Constraints

Receipt binds task, requirements, card, agent, revision, and expiry.

## Requirement

### REQ-F-502 - Enforce routed task receipts

The tool shall dispatch only eligible agents with a matching one-use receipt and structured completion report.

## Example

`route` rejects worker dispatch without a confirmed execution card.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
