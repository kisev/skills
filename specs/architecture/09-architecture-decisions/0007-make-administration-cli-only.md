# ADR-0007: Make Administration CLI-Only

- Status: accepted
- Date: 2026-09-16

## Context

OpenCode slash commands and package tools duplicated deterministic operations
already implemented by `skills-opencode`. Invoking those operations through an
agent added latency and token cost without adding reasoning. The portable
`lsp-report` skill also duplicated the LSP inventory in the direct doctor CLI.

## Decision

Keep package administration only in the direct `skills-opencode` CLI. Retire the
`agent-profiles`, `capabilities`, `doctor`, and `reconcile` slash commands and
package tools. Keep `route` as the sole package tool because it enforces native
Task routing receipts. Retire the portable `lsp-report` skill and its command;
`skills-opencode doctor` becomes the supported LSP reporting interface.

## Alternatives

We rejected retaining command adapters without tools because they would have no
execution target. We rejected retaining tools without commands because agents
could still spend tokens invoking deterministic administration. We rejected
keeping `lsp-report` for portability because this repository no longer needs an
LSP interface outside the OpenCode package.

## Consequences

The public inventory becomes `27/27/6/3/1`. Existing managed commands and the
portable `lsp-report` skill are retired through migration cleanup. CLI behavior,
transactional confirmation, rollback, diagnostics, profiles, and reconciliation
remain unchanged. Global user configuration is not changed by this source update.

## Links

Supersedes [ADR-0006](0006-retire-generic-doit-coordinator.md).
