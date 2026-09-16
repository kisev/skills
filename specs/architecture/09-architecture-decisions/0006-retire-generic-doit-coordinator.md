# ADR-0006: Retire Generic Doit Coordinator

- Status: superseded by [ADR-0007](0007-make-administration-cli-only.md)
- Date: 2026-09-16
- Status changed: 2026-09-16

## Context

The generic `doit` skill duplicated normal host engineering behavior and required
a preview artifact and authorization lifecycle for ordinary local changes. This
made development slower and left agents uncertain about when to select the skill.

## Decision

Retire the portable `doit` skill and `/doit` command without a replacement.
Normal engineering execution belongs to the host agent and repository guidance.
The OpenCode `manager` owns its host-specific routed lifecycle, while reusable
Goal Mode policy validation remains shared by the workflows that require it.

## Alternatives

We rejected keeping a slimmer generic skill because it would still overlap the
host's primary role. We also rejected turning `doit` into a strict patch-apply
runtime because that is a distinct capability without a current product need.

## Consequences

The public inventory becomes `28/32/6/3/5`. Existing installed `doit` skills and
commands are retired through migration inventory cleanup. Portable skills remain
domain-specific, and default coding behavior follows the active host and
repository instructions.

## Links

Supersedes [ADR-0002](0002-target-public-surface.md) and
[ADR-0003](0003-portable-coordinator-routing-adapter.md).

## Supersession

[ADR-0007](0007-make-administration-cli-only.md) further reduced the public
surface by making package administration CLI-only and retiring `lsp-report`.
