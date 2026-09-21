# ADR-0006: Retire Generic Doit Coordinator

- Status: superseded
- Date: 2026-09-16
- Status changed: 2026-09-16
- Supersedes: [ADR-0002](0002-target-public-surface.md), [ADR-0003](0003-portable-coordinator-routing-adapter.md)
- Superseded by: [ADR-0007](0007-make-administration-cli-only.md)

## Context and problem statement

The generic `doit` skill duplicated normal host engineering behavior and required
an authorization lifecycle for ordinary local changes, slowing development and
making selection ambiguous.

## Decision drivers

- One clear owner for ordinary engineering execution.
- Portable skills remain domain-specific and host-neutral.
- Preserve reusable Goal Mode policy only where workflows require it.

## Considered options

- Retire `doit` and assign ordinary execution to the host.
- Keep a slimmer generic coordinator.
- Convert `doit` into a strict patch-apply runtime.

## Outcome

Retire the portable `doit` skill and command without a replacement. Ordinary
engineering execution belongs to the host; OpenCode `manager` owns host-specific
routing, and workflows retain reusable Goal Mode policy where required.

## Consequences

### Positive

- Portable capabilities have clearer ownership and no generic coordination overlap.

### Negative

- Default coding behavior depends on the active host and repository instructions.

## Compatibility

The public inventory changed to `28/32/6/3/5`; the retired `doit` interfaces are unsupported.

## Migration

Installed `doit` assets are classified as retired under the package ownership contract.

## Rollback

Restoring `doit` would require a new explicit portable capability and public-surface decision.

## Reversibility

The removal is reversible only by recreating the retired API and resolving its ownership overlap.

## Risks

- Host-specific behavior can diverge; repository guidance and domain workflows bound expected execution.

## Links

- Requirements: [REQ-F-001](../../requirements/functional/README.md#req-f-001---expose-the-verified-capability-surface), [REQ-F-002](../../requirements/functional/README.md#req-f-002---route-work-through-bounded-orchestration), [REQ-C-005](../../requirements/constraints/README.md#req-c-005---bounded-distribution-change-in-this-target)
- Related ADRs: [ADR-0002](0002-target-public-surface.md), [ADR-0003](0003-portable-coordinator-routing-adapter.md), [ADR-0007](0007-make-administration-cli-only.md)
