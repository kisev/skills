# ADR-0001: Direct Git Self-Contained Skills

- Status: superseded
- Date: 2026-09-10
- Status changed: 2026-09-14
- Supersedes: none
- Superseded by: [ADR-0005](0005-github-pages-well-known-distribution.md)

## Context and problem statement

Portable skills must work independently of the OpenCode package and preserve
their references when installed directly from Git.

## Decision drivers

- Host portability and self-contained installed skills.
- A narrow consumer trust boundary.

## Considered options

- Keep canonical skill material and references in the Git distribution.
- Make portable skills depend on the OpenCode package.
- Load shared references through a runtime dependency.

## Outcome

The original decision kept canonical skill material and required references in
the Git distribution and used committed materialization rules rather than a
runtime package dependency. [ADR-0005](0005-github-pages-well-known-distribution.md)
superseded that distribution mechanism while preserving self-contained archives.

## Consequences

### Positive

- Direct installation was self-contained and auditable.

### Negative

- Committed generated copies obscured canonical ownership and required duplicate maintenance.

## Compatibility

The original contract supported direct Git installation; ADR-0005 replaced that
installation source with GitHub Pages archives.

## Migration

Superseded by ADR-0005's one-time rebinding from Git to the Pages source.

## Rollback

Historical tags retain the original direct-Git contract; current releases do not
roll back to committed materialization.

## Reversibility

Reversal would require restoring generated Git materialization and its parity
contract, so it is costly but technically possible.

## Risks

- Historical direct-Git installations remain distinct from the current distribution contract.

## Links

- Requirements: [REQ-I-001](../../requirements/interfaces/README.md#req-i-001---skill-interface), [REQ-C-002](../../requirements/constraints/README.md#req-c-002---portable-distribution-boundary)
- Related ADRs: [ADR-0005](0005-github-pages-well-known-distribution.md)
