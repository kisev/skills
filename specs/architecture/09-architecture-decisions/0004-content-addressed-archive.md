# ADR-0004: Content-Addressed Archive

- Status: accepted
- Date: 2026-09-10

## Context

Retired exact-owned assets need recoverability without deleting user content or
historical state.

## Decision

Reconciliation archives owned retired assets by content address and leaves
unrelated files and durable state unchanged.

## Alternatives

We rejected destructive cleanup and an unbounded timestamp-only archive because
they lose recovery guarantees or permit duplicate and ambiguous ownership.

## Consequences

Archival is auditable and repeatable. Archive storage and digest validation are
part of the lifecycle boundary.
