# ADR-0001: Direct Git Self-Contained Skills

- Status: superseded by [ADR-0005](0005-github-pages-well-known-distribution.md)
- Date: 2026-09-10
- Status changed: 2026-09-14

## Context

Portable skills must work independently of the OpenCode package and preserve
their references when installed directly from Git.

## Decision

Keep canonical skill material and required references in the Git distribution;
use committed materialization rules rather than a runtime package dependency.

## Alternatives

We rejected package-only distribution and a shared runtime dependency because
either breaks host portability or expands the trust boundary.

## Consequences

Direct installation is self-contained and auditable. Generated parity and
duplicate maintenance remain necessary.

## Supersession

[ADR-0005](0005-github-pages-well-known-distribution.md) replaced committed
materialization with release-built, content-addressed Pages archives because
committed generated copies obscure canonical ownership and create drift.
