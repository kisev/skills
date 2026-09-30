# `lsp-report`

- Status: withdrawn
- Status changed: 2026-09-16
- Reason: `agentomatic doctor` is the single supported LSP reporting interface.

## Purpose

Historical capability record for the retired portable LSP reporter.

## Triggers and Near-Misses

Trigger for LSP inventory; near-miss: installing or enabling a server.

## Inputs and Outputs

Input is repository/config scope. Output is active and inactive server facts.

## Workflow Stages

Resolve scope, read config, classify servers, report applicability and gaps.

## Dependencies

Local configuration and bundled catalog.

## Remote/Local Effects

Local reads only; no process start, install, or remote effect.

## Errors, Partial, Escalation

Unreadable config is partial; unsupported server requests are escalated.

## Unique Constraints

The report never starts an LSP or installs dependencies.

## Requirement

### REQ-F-112 - Keep LSP reporting observational

Status: withdrawn on 2026-09-16 because the portable skill was replaced by the
direct `agentomatic doctor` CLI.

Former requirement: the skill shall report LSP state without starting servers or
changing configuration.

## Example

`lsp-report` marks a disabled configured server as inactive.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
