# ADR-0001: Direct Git Self-Contained Skills

- Status: accepted
- Date: 2026-09-10

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
