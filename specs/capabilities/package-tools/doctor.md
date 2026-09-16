# Package Tool `doctor`

- Status: withdrawn
- Status changed: 2026-09-16
- Reason: Diagnostics remain available through `skills-opencode doctor`.

## Purpose

Historical capability record for the retired OpenCode package tool.

## Triggers and Near-Misses

Trigger for diagnostics; near-miss: automatic repair.

## Inputs/Outputs

Input is optional global/project scope defaulting to project; output is
structured, redacted facts.

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

Status: withdrawn on 2026-09-16 because diagnostics are now CLI-only.

Former requirement: the tool shall inspect health without writing and shall never
serialize secrets.

## Example

`doctor` reports an inaccessible symlink as a bounded problem.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
