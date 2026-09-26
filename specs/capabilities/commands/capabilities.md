# `/capabilities`

- Status: withdrawn
- Status changed: 2026-09-16
- Reason: Package inventory remains available through `agentomatic capabilities`.

## Purpose

Historical capability record for the retired slash-command adapter.

## Triggers and Near-Misses

Trigger for package inventory; near-miss: installation or repair.

## Inputs/Outputs

Input is empty; output is versioned catalog JSON.

## Workflow Stages

Resolve package, read catalog, serialize, report.

## Dependencies

Core plugin catalog.

## Remote/Local Effects

Read-only local/package effect.

## Errors/Partial/Escalation

Catalog drift is an error and must not be hidden.

## Unique Constraints

No install, config, or state mutation.

## Requirement

### REQ-I-230 - Route the capabilities package command

Status: withdrawn on 2026-09-16 because package inventory is now CLI-only.

Former requirement: the command shall expose the exact empty argument schema,
invoke package tool `capabilities`, and return its versioned catalog.

## Example

`/capabilities` returns the current public inventory.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
