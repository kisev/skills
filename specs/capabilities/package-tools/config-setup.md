# Package Command `config`

- Status: active
- Status changed: 2026-09-30

## Purpose

Connect `@kisev/agentomatic` and recommended configuration fragments into
user-owned OpenCode, Kilo Code, and MiMo Code configuration files through a
confirmed interactive or flag-driven setup.

## Triggers and Near-Misses

Trigger for first-time activation, standard skills state permissions, secret
guards, or terminal presets; near-miss: repairing arbitrary user configuration, installing
portable skills, or mutating provider credentials.

## Inputs/Outputs

Input is optional global/project scope defaulting to project, target selection
(`opencode`, `kilo`, `mimo`), and fragment selection (`core-plugin`,
`skills-state-permissions`, `secrets-guard`, `kilo-display`,
`tui-schema`); output is a preview or applied plan with per-target and
per-fragment operations, conflicts, and skipped fragments.

## Workflow Stages

Resolve target files, read current JSONC, merge fragments, validate the merged
document, preview with a one-time confirmation receipt, apply transactionally,
verify written bytes. Receipts live in the invoking process, expire after five
minutes, and bind source bytes, selection, scope, package version, and dependency
plan. A separate dry-run invocation is informational; interactive apply previews
and confirms within one process, while `--yes` authorizes a fresh bounded plan.

## Dependencies

Lifecycle receipts and transactions, native V2 config normalization, and the
in-package JSONC editor. The shared LSP catalog remains available to other
consumers; config setup does not offer a nonfunctional V2 LSP preset.

## Remote/Local Effects

Bounded local writes to user configuration files under `~/.config/opencode`,
`~/.config/kilo`, `~/.config/mimocode`, and the project `opencode.json(c)`.
The selected `core-plugin` fragment may provision the npm dependency, accessing
the registry and changing `package.json`, `package-lock.json`, and `node_modules`.
The preview declares that dependency plan. No portable skill mutation occurs.

## Errors/Partial/Escalation

Stale, expired, or replayed receipts fail before writing. A fragment that
cannot merge cleanly is reported as a conflict and skipped without blocking
the remaining plan. Failed transactions roll back to the previewed state.
Preview never creates a lock or performs recovery. A pending transaction stops
preview and apply. `config recover --dry-run` lists the affected paths without
writing; confirmed `config recover` binds restoration to that journal's digest
and requires a fresh config preview afterwards. Dependency provisioning is a separate
effect: an npm failure after config commit reports failure and requires a retry;
it does not claim to roll back npm's files or the completed config transaction.

## Unique Constraints

Existing comments, unrelated entries, and user values are preserved. Native
OpenCode output and bounded legacy-section conversion follow
[REQ-I-420](../../requirements/interfaces/README.md#req-i-420---native-opencode-v2-interface).
Permission scalars become wildcard rules; converted aliases use native actions.
Kilo/MiMo scalar permission maps retain the scalar as the `"*"` entry. Every
written document must reparse as valid JSONC. A confirmed `install`
with core selected applies this fragment under REQ-F-010. Its dependency opt-out
applies through the entire path; `uninstall` never edits user configuration.

## Requirement

### REQ-F-514 - Merge config fragments non-destructively

Status: active since 2026-09-26.

The `config` command shall merge selected fragments into user configuration
files only after a confirmed preview, preserve user entries and comments, add
only absent preset values except for the behavior-preserving native conversion
of touched legacy sections under REQ-I-420, validate every merged document before and after writing, and
roll the whole plan back on any failed postcondition. The `core-plugin`
fragment shall register `@kisev/agentomatic` as an exact-version registry spec
pinned to the running package version, because OpenCode V2 resolves a bare
package name through the registry `latest` dist-tag, which can select an
unrelated build. Any existing `@kisev/agentomatic` or legacy
`@kisev/skills-opencode` entry — bare, stale-pinned, or with options — shall be
replaced by that pinned spec in place instead of appending a duplicate, leaving
unrelated user plugins untouched.

#### Verification

`packages/agentomatic/test/config-setup.test.mjs` checks preserved user entries,
stale and replayed receipts, non-mutating previews, pending recovery, dependency
opt-out, and archived pre-images. CLI integration tests check core activation.

## Example

`config --global --dry-run` converts a legacy OpenCode
`"external_directory": "ask"` effect to an ordered wildcard rule and previews
the selected skills-state exceptions after it. Kilo/MiMo retain map widening.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
