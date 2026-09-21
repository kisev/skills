# ADR-0007: Make Administration CLI-Only

- Status: accepted
- Date: 2026-09-16
- Status changed: none
- Supersedes: [ADR-0006](0006-retire-generic-doit-coordinator.md)
- Superseded by: none

## Context and problem statement

OpenCode slash commands and package tools duplicated deterministic operations
already implemented by `skills-opencode`; portable `lsp-report` also duplicated
the LSP inventory in the direct doctor CLI.

## Decision drivers

- Avoid agent latency and token cost for deterministic administration.
- Keep one supported owner for package administration and LSP reporting.
- Preserve only the package tool required for host routing.

## Considered options

- Keep administration only in the direct CLI.
- Retain command adapters without package tools.
- Retain package tools without commands.
- Keep portable `lsp-report` as a second reporting surface.

## Outcome

Keep package administration only in `skills-opencode`. Retire the
`agent-profiles`, `capabilities`, `doctor`, and `reconcile` slash commands and
package tools. Keep `route` as the sole package tool, and use
`skills-opencode doctor` as the supported LSP reporting interface.

## Consequences

### Positive

- Deterministic administration has one direct, lower-cost interface.

### Negative

- Removed command and tool surfaces are no longer available to agent workflows.

## Compatibility

The public inventory becomes `27/27/6/3/1`; retained CLI behavior and the declared OpenCode range are unchanged.

## Migration

Retired managed command, tool, and `lsp-report` assets follow existing ownership-safe cleanup; global user configuration is unchanged.

## Rollback

CLI mutation rollback remains unchanged. Restoring removed public surfaces would require a new decision and contracts.

## Reversibility

The architecture is reversible only by reintroducing duplicate interfaces and their compatibility obligations.

## Risks

- Consumers relying on retired adapters must invoke the direct CLI instead; contextual CLI help provides the supported surface.

## Links

- Requirements: [REQ-F-001](../../requirements/functional/README.md#req-f-001---expose-the-verified-capability-surface), [REQ-F-007](../../requirements/functional/README.md#req-f-007---provide-observational-health-and-inventory), [REQ-I-003](../../requirements/interfaces/README.md#req-i-003---package-tool-interface), [REQ-C-005](../../requirements/constraints/README.md#req-c-005---bounded-distribution-change-in-this-target)
- Related ADRs: [ADR-0006](0006-retire-generic-doit-coordinator.md)
