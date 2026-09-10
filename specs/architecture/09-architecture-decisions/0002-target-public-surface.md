# ADR-0002: Target Public Surface

- Status: accepted
- Date: 2026-09-10

## Context

The merged package and source catalogs define a bounded public surface.

## Decision

The supported target is exactly `29/33/6/3/5`: skills, commands, agents,
selectable plugins, and package tools. The core infrastructure plugin is separate
from selectable plugins.

## Alternatives

We rejected exposing generated internals and retaining retired APIs because that
would make inventory and compatibility ambiguous.

## Consequences

Catalog parity is machine-checkable. Adding a surface requires an explicit
contract and corresponding evidence.
