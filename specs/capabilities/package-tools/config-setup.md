# Package Command `config`

- Status: active
- Status changed: 2026-09-26

## Purpose

Connect `@kisev/skills-opencode` and recommended configuration fragments into
user-owned OpenCode, Kilo Code, and MiMo Code configuration files through a
confirmed interactive or flag-driven setup.

## Triggers and Near-Misses

Trigger for first-time activation, standard skills state permissions, or LSP
preset setup; near-miss: repairing arbitrary user configuration, installing
portable skills, or mutating provider credentials.

## Inputs/Outputs

Input is optional global/project scope defaulting to project, target selection
(`opencode`, `tui`, `kilo`, `mimo`), and fragment selection (`core-plugin`,
`skills-state-permissions`, `lsp-preset`, `secrets-guard`, `kilo-display`,
`tui-schema`); output is a preview or applied plan with per-target and
per-fragment operations, conflicts, and skipped fragments.

## Workflow Stages

Resolve target files, read current JSONC, merge fragments, validate the merged
document, preview with a one-time confirmation receipt, apply transactionally,
verify written bytes.

## Dependencies

Lifecycle receipts and transactions, the shared LSP catalog asset, and the
in-package JSONC editor.

## Remote/Local Effects

Bounded local writes to user configuration files under `~/.config/opencode`,
`~/.config/kilo`, `~/.config/mimocode`, and the project `opencode.json(c)`.
No network access and no portable skill mutation.

## Errors/Partial/Escalation

Stale, expired, or replayed receipts fail before writing. A fragment that
cannot merge cleanly is reported as a conflict and skipped without blocking
the remaining plan. Failed transactions roll back to the previewed state.

## Unique Constraints

Existing keys, comments, unrelated entries, and user values are never
overwritten; only absent keys are added, arrays gain only missing entries, and
a scalar permission map widens to a map that keeps the scalar as the `"*"`
entry. Every written document must reparse as valid JSONC. `install` and
`uninstall` still never edit user configuration files.

## Requirement

### REQ-F-514 - Merge config fragments non-destructively

Status: active since 2026-09-26.

The `config` command shall merge selected fragments into user configuration
files only after a confirmed preview, preserve user entries and comments, add
only absent keys, validate every merged document before and after writing, and
roll the whole plan back on any failed postcondition.

## Example

`config --global --dry-run` widens `"external_directory": "ask"` into a map
that keeps `"*": "ask"` and adds `~/.local/state/agent-skills/**` as allowed.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
