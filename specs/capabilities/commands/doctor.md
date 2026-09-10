# `/doctor`

## Purpose

Inspect package integration health without installing or repairing.

## Triggers and Near-Misses

Trigger for diagnostics; near-miss: configuration mutation.

## Inputs/Outputs

Input is global/project scope; output is structured health facts.

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

The command shall invoke package tool `doctor` and remain observational.

## Example

`/doctor` reports project health without editing configuration.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
