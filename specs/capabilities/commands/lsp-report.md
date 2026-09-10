# `/lsp-report`

## Purpose

Expose the observational `lsp-report` command.

## Triggers and Near-Misses

Routes LSP reporting; near-miss: installation.

## Inputs/Outputs

Arguments select scope; output is active/inactive catalog facts.

## Workflow Stages

Select, pass, inspect, classify, report.

## Dependencies

`lsp-report` and local config.

## Remote/Local Effects

Read-only; no server start.

## Errors/Partial/Escalation

Unreadable config remains partial.

## Unique Constraints

No dependency installation.

## Requirement

### REQ-I-212 - Route the lsp-report command

The command shall load exactly `lsp-report` and remain observational.

## Example

`/lsp-report` reports configured LSP status.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
