# ADR-0004: Content-Addressed Archive

- Status: accepted
- Date: 2026-09-10
- Status changed: none
- Supersedes: none
- Superseded by: none

## Context and problem statement

Retired exact-owned assets need recoverability without deleting user content or
historical state.

## Decision drivers

- Recovery and auditability for retired owned assets.
- Strict separation from unrelated user-owned files and durable state.

## Considered options

- Archive owned retired assets by content address.
- Delete retired assets destructively.
- Use an unbounded timestamp-only archive.

## Outcome

Reconciliation archives owned retired assets by content address and leaves
unrelated files and durable state unchanged.

## Consequences

### Positive

- Archival is auditable, deduplicated, and repeatable.

### Negative

- Archive storage and digest validation become part of the lifecycle boundary.

## Compatibility

Existing archived content remains addressable by digest; unrelated user state is unchanged.

## Migration

Not applicable: the decision defines handling of future retired owned assets, not a format transition.

## Rollback

Archived bytes provide the recovery source for restoring an owned asset.

## Reversibility

The mechanism is reversible per asset while retained archives remain intact.

## Risks

- Corrupt or unbounded archive storage can weaken recovery; digest validation and ownership bounds contain the risk.

## Links

- Requirements: [REQ-F-005](../../requirements/functional/README.md#req-f-005---archive-owned-retired-assets), [REQ-Q-002](../../requirements/quality/README.md#req-q-002---mutation-safety), [REQ-C-004](../../requirements/constraints/README.md#req-c-004---no-destructive-cleanup)
- Related ADRs: None; no other decision changes this archive boundary.
