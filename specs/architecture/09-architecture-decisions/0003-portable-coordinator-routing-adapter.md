# ADR-0003: Portable Coordinator and Routing Adapter

- Status: superseded
- Date: 2026-09-10
- Status changed: 2026-09-16
- Supersedes: none
- Superseded by: [ADR-0006](0006-retire-generic-doit-coordinator.md)

## Context and problem statement

Workflows had to remain portable while OpenCode required host-aware orchestration.

## Decision drivers

- Host-neutral portable skills.
- Central enforcement of host routing receipts.

## Considered options

- Keep `doit` as portable coordinator and OpenCode as routing adapter.
- Embed host routing in every skill.
- Replace native Task with a package-specific executor.

## Outcome

The original decision kept `doit` as the portable coordinator and made the
OpenCode package a routing adapter that resolved host agents and enforced
receipts. ADR-0006 removed the generic portable coordinator and assigned
OpenCode-specific coordination to `manager`.

## Consequences

### Positive

- Skills remained host-neutral while routing validation stayed centralized.

### Negative

- The generic coordinator duplicated host engineering behavior and added authorization overhead.

## Compatibility

ADR-0006 removed the portable `doit` surface while retaining host-specific routing.

## Migration

The target state moves generic coordination to the host and keeps OpenCode-specific coordination in `manager`.

## Rollback

Restoring `doit` would require a new public capability and routing contract.

## Reversibility

Reversal is possible but costly because it would recreate a retired portable API and overlapping ownership.

## Risks

- Host behavior may differ where no domain-specific portable workflow owns coordination.

## Links

- Requirements: [REQ-F-002](../../requirements/functional/README.md#req-f-002---route-work-through-bounded-orchestration), [REQ-C-002](../../requirements/constraints/README.md#req-c-002---portable-distribution-boundary)
- Related ADRs: [ADR-0006](0006-retire-generic-doit-coordinator.md)
