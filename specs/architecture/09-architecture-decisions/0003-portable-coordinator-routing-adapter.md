# ADR-0003: Portable Coordinator and Routing Adapter

- Status: accepted
- Date: 2026-09-10

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
