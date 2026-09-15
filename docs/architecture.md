# Architecture

[Русский](ru/architecture.md)

## Source of Truth

Portable definitions live in `skills/<name>/` with authored
`SKILL.source.md` entrypoints and unique resources. `shared/` is the single
source for common contracts and runtime, not an installed dependency. The
declarative `shared/manifest.json` maps exact shared files into build paths.
`scripts/build_skills.py` creates complete skills only under `.build/skills` and
never writes generated copies into the authored tree. Authored and built skill
metadata carries no version.

The repository has no user CLI and is intentionally not a portable installation
source. Maintainer scripts use Python standard library only, while every built
runner and referenced resource belongs inside its owning skill archive.

Shared English contracts are injected from `shared/references/`; schemas and
`work_item.py` remain canonical machine inputs. In particular,
`shared/references/work-item-contract.schema.json` is built into `task-prepare`
and `task-review`; its validator can return `needs_clarification`. Installed
skills never read `shared/`.

`packages/skills/package.json` is the private version manifest for the portable
distribution. `scripts/build_distribution.py` produces the GitHub Pages payload
under `.build/packages/skills`: a standard well-known index, release metadata,
and one content-addressed SHA-256 archive with root `SKILL.md` per skill. The
distribution metadata and each archive digest define release identity instead of
skill metadata. The single tag workflow runs the complete gate, records hashes
for every Pages file and the exact npm tarball, publishes both channels, verifies
their remote bytes and npm provenance, then creates the GitHub Release.

## Host Integration

Portable skills are host-neutral. `packages/opencode/` is optional and contains
OpenCode-specific assets only; it does not contain copied skills. OpenCode
commands, the LSP catalog, and authored agent/plugin assets are materialized to
`packages/opencode/dist/assets/` before `npm pack`. Its installer applies those
assets only after dry-run and a matching digest, preserving user drift through
ownership manifests. Agent assets hold prompts and permissions; profile
configuration holds models, variants, and additional critics. Stateful plugins
are opt-in and create no state, timers, sessions, or mutations while disabled.

## OpenCode Runtime

Materialized runners use only their own files and XDG state. Package tools do
not make portable skills depend on the checkout. Package assets are materialized
in `packages/opencode/dist/assets`, and unavailable host facts are explicitly
`unavailable/incomplete`. The optional `agent_profiles` adapter does not change
those boundaries. Specialized Python-runner skills remain ordinary self-contained
Agent Skills; `goal` is a read-only prompt-only adapter. `doctor` shares a
versioned read-only facts API with the direct CLI and never invokes plugin
factories, lifecycle recovery, receipts, journals, or LSP servers. Routing and
mutation receipts are private, one-time, TTL-bound, and reject stale or replayed
inputs. Stateful records use private atomic writes and locks; incomplete
background attempts become `orphaned` on reload.

### Stage 18 Routing Contracts

`doit` is the sole owner of the evidence -> plan -> confirmation -> execution ->
checks -> report lifecycle. The OpenCode `manager` is only a thin adapter. The
package route tool has four destinations: exploration to `mapper`, architecture
to `architect`, implementation to `worker`, and review to `review` or one
selected `critic`; documentation and quick work stay in `doit`.

Routing inventory is resolved from host configuration. Route callers cannot inject
agents, capabilities, tools, models, or availability. Versioned routing receipts
are one-use, TTL-bound, and bind task, requirements, destination, agent, execution
card, and host inventory revision. Versioned execution cards and mapper, worker,
review, and critic reports are checked at the real Task dispatch and result hooks.
Cards close write and forbidden paths, checks, explicit VCS operations, and
separate execution, publication, and history-rewrite confirmations.

## Build Invariants

- The JSON manifest maps canonical shared inputs to build-only paths.
- Authored skill trees contain `SKILL.source.md` and no generated destination.
- Authored and built skill frontmatter has no version field.
- `--check` reports source and artifact drift without changing authored files.
- The supported installer reads the well-known Pages index and verifies each
  archive digest before installation.
- Paths are normalized, relative, and constrained to the shared references and
  isolated output; source and destination symlinks are rejected.
- Source is unchanged and output is replaced only after complete staging.
- Release checks bind the Pages version and source revision to the exact tag.
- Release publication promotes only preflighted artifacts and verifies both
  remote channels before creating the GitHub Release.
- Work-item findings have stable sort order and bind reports to item/evidence
  digests, so unchanged checks produce the same verdict.
