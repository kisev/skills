# `/stopit`

## Purpose

Expose temporary anonymized handoff creation.

## Triggers and Near-Misses

Routes session handoff; near-miss: repository notes.

## Inputs/Outputs

Arguments provide session context; output is temporary handoff path.

## Workflow Stages

Select, pass, redact, write temp artifact, verify, report.

## Dependencies

`stopit` and OS temporary directory.

## Remote/Local Effects

Temporary write only.

## Errors/Partial/Escalation

Redaction uncertainty blocks.

## Unique Constraints

No repository file is created.

## Requirement

### REQ-I-221 - Route the stopit command

The command shall load exactly `stopit` and preserve temporary-only storage.

## Example

`/stopit` writes an anonymized handoff outside the repository.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
