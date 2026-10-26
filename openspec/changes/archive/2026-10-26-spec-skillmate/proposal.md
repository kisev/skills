# Proposal

## Why

The installer-configurator was renegotiated from the foundation (see
`renegotiate-foundation`, capabilities `distribution` and `stack`): the
TypeScript OpenCode-only `@kisev/agentomatic` npm integration and the
external `skills` CLI as the primary channel do not fit the renegotiated
model. This change gives the component its exhaustive specification and
executes the renegotiation decisions that concern it.

Owner decisions recorded during clarification:

- The tool is renamed to **skillmate** (the PyPI name `agentomatic` is
  taken by an unrelated active project; `skillmate` is free and claimed by
  the owner's account `kisev`).
- Content sources: the versioned Pages distribution is the primary,
  always-available channel (minimum compatibility with `npx skills`
  stays); a local checkout is a dev-only mode for unpublished or
  experimental versions and is never required.
- Placement follows the openspec delivery model: per-host directories
  (`.agents` for Codex, `.claude` for Claude, `.opencode` for OpenCode) in
  both project and global scopes, with per-host dialect materialization.
- Delivery is PyPI: `pip install skillmate` and `uvx skillmate`.
- The npm line, the six fixed agents, and the capability routing layer
  are removed completely, without deprecation pointers or mentions.

## What Changes

`skillmate` becomes the single installer-configurator for skills,
commands, and host configuration across Codex, Claude, and OpenCode, in
project and global scopes, over a host-adapter registry with one
canonical content model. The safety model of the retired npm integration
(preview, explicit confirmation, ownership manifests, drift
preservation) is ported as contracts into a fresh, small Python
implementation under `apps/skillmate/`.

The exhaustive capability spec, the adapter design, and the removal plan
for the retired surfaces are drafted inside this change.

## Capabilities

### New Capabilities

- `skillmate` — the exhaustive specification drafted in this change.

### Modified Capabilities

None.

## Impact

`apps/skillmate/` (new), `packages/agentomatic/` (deleted with its npm
publication graph), `docs/` (install how-to EN/RU, CLI reference),
`mise.toml`, the release automation, and the Pages distribution contract
(consumer, unchanged producer).
