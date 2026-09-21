# ADR-0002: Target Public Surface

- Status: superseded
- Date: 2026-09-10
- Status changed: 2026-09-16
- Supersedes: none
- Superseded by: [ADR-0006](0006-retire-generic-doit-coordinator.md)

## Context and problem statement

The merged package and source catalogs required one bounded, machine-checkable
public surface.

## Decision drivers

- Unambiguous public inventory and compatibility checks.
- Exclusion of generated internals and retired APIs.

## Considered options

- Declare an exact public inventory.
- Expose generated internals.
- Retain retired APIs as part of the supported surface.

## Outcome

The supported target was set to exactly `29/33/6/3/5`: skills, commands, agents,
selectable plugins, and package tools. The core infrastructure plugin remained
separate from selectable plugins. ADR-0006 later reduced this inventory.

## Consequences

### Positive

- Catalog parity became machine-checkable.

### Negative

- Every public-surface change requires an explicit contract and matching evidence.

## Compatibility

The exact inventory was itself a compatibility boundary and changed when ADR-0006 superseded this decision.

## Migration

Superseded by ADR-0006's smaller public inventory; no implementation sequence is part of this record.

## Rollback

Restoring the former inventory would require a new decision and restored public contracts.

## Reversibility

The decision was reversible only through a coordinated public-surface change.

## Risks

- Consumers of removed entries require an explicit replacement or unsupported-boundary statement.

## Links

- Requirements: [REQ-F-001](../../requirements/functional/README.md#req-f-001---expose-the-verified-capability-surface), [REQ-C-005](../../requirements/constraints/README.md#req-c-005---bounded-distribution-change-in-this-target)
- Related ADRs: [ADR-0006](0006-retire-generic-doit-coordinator.md)
