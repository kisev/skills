# Package Tool `capabilities`

- Status: withdrawn
- Status changed: 2026-09-16
- Reason: Package inventory remains available through `skills-opencode capabilities`.

## Purpose

Historical capability record for the retired OpenCode package tool.

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

Status: withdrawn on 2026-09-16 because package inventory is now CLI-only.

Former requirement: the tool shall report the exact public inventory and
core/plugin distinction.

## Example

`capabilities` returns schema version `1` and the current package version.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
