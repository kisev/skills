# Package Tool `capabilities`

- Status: withdrawn
- Status changed: 2026-09-16
- Reason: Package inventory remains available through `agentomatic capabilities`.

## Purpose

Historical capability record for the retired OpenCode package tool.

## Triggers and Near-Misses

Trigger for inventory inspection; near-miss: install or repair.

## Inputs/Outputs

Input is none; output is versioned JSON inventory.

## Workflow Stages

Read catalog, serialize stable fields, report.

## Dependencies

`packages/agentomatic/src/catalog.ts`.

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

## Requirement

### REQ-F-516 - Migrate legacy skills-opencode namespaces on upgrade

Status: active since 2026-09-26.

The installer shall move the legacy ownership namespaces exactly once when the
target is absent: the XDG state and data `opencode/skills-opencode/` trees to
`opencode/agentomatic/` before any lifecycle lock or receipt is written, and the
deployment `.skills-opencode/` directory to `.agentomatic/` inside the confirmed
apply transaction. Every move shall preserve bytes and modes, refuse symlinks,
skip when both namespaces exist, and never touch user configuration beyond the
owned deployment directory. Preview and reconcile shall read the generic and
semantic ownership manifests through the new names first and the legacy names
as fallback so unupgraded deployments remain visible without mutation.

## Example

`capabilities` returns schema version `1` and the current package version.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
