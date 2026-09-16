# `/doctor`

- Status: withdrawn
- Status changed: 2026-09-16
- Reason: Diagnostics remain available through `skills-opencode doctor`.

## Purpose

Historical capability record for the retired slash-command adapter.

## Triggers and Near-Misses

Trigger for diagnostics; near-miss: configuration mutation.

## Inputs/Outputs

Input is optional global/project scope defaulting to project; output is
structured health facts.

## Workflow Stages

Resolve scope, read host facts, classify, redact, report.

## Dependencies

Core doctor package tool and host APIs.

## Remote/Local Effects

Read-only configuration/LSP reads.

## Errors/Partial/Escalation

Malformed state is incomplete; secrets are never returned.

## Unique Constraints

No repair or install.

## Requirement

### REQ-I-231 - Route the doctor package command

Status: withdrawn on 2026-09-16 because diagnostics are now CLI-only.

Former requirement: the command shall expose the exact package-tool argument schema, default omitted
scope to project, invoke package tool `doctor`, and remain observational.

## Example

`/doctor` reports project health without editing configuration.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
