# ADR-0003: Portable Coordinator and Routing Adapter

- Status: superseded by [ADR-0006](0006-retire-generic-doit-coordinator.md)
- Date: 2026-09-10
- Status changed: 2026-09-16

## Context

Workflows must remain portable while OpenCode needs host-aware orchestration.

## Decision

`doit` remains the portable coordinator. The OpenCode package is a routing
adapter that resolves host agents and enforces receipts around native Task calls.

## Alternatives

We rejected embedding host routing in every skill and replacing native Task with
a package-specific executor because both fragment contracts and reduce portability.

## Consequences

Skills stay host-neutral. The adapter must validate host inventory, receipt
freshness, structured reports, and execution-card requirements.

## Supersession

[ADR-0006](0006-retire-generic-doit-coordinator.md) removed the generic portable
coordinator because it duplicated host engineering behavior and imposed a costly
authorization workflow on ordinary development. OpenCode-specific coordination
now belongs to `manager`.
