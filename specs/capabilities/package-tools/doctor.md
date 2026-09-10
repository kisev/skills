# Package Tool `doctor`

## Purpose

Inspect package integration health and opt-in defaults.

## Triggers and Near-Misses

Trigger for diagnostics; near-miss: automatic repair.

## Inputs/Outputs

Input is global/project scope; output is structured, redacted facts.

## Workflow Stages

Resolve scope, collect config/LSP/state facts, classify, report.

## Dependencies

Host config/LSP APIs and local package state.

## Remote/Local Effects

Read-only local/host reads.

## Errors/Partial/Escalation

Malformed state is incomplete; collisions are problems.

## Unique Constraints

No install, repair, or config mutation.

## Requirement

### REQ-F-503 - Keep doctor observational

The tool shall inspect health without writing and shall never serialize secrets.

## Example

`doctor` reports an inaccessible symlink as a bounded problem.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
