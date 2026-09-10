# `/capabilities`

## Purpose

List the bundled OpenCode capability catalog without changing anything.

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

The command shall invoke package tool `capabilities` and return its versioned catalog.

## Example

`/capabilities` returns the `2.0.0` public inventory.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
