# Package Tool `capabilities`

## Purpose

Return the bundled package capability catalog.

## Triggers and Near-Misses

Trigger for inventory inspection; near-miss: install or repair.

## Inputs/Outputs

Input is none; output is versioned JSON inventory.

## Workflow Stages

Read catalog, serialize stable fields, report.

## Dependencies

`packages/opencode/src/catalog.ts`.

## Remote/Local Effects

Read-only.

## Errors/Partial/Escalation

Catalog drift is an error.

## Unique Constraints

The tool never changes configuration or state.

## Requirement

### REQ-F-501 - Report package inventory

The tool shall report the exact `29/33/6/3/5` inventory and core/plugin distinction.

## Example

`capabilities` returns schema version `1` and package version `2.0.0`.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
