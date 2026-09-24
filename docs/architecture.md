# Architecture

[Русский](ru/architecture.md)

## Source of Truth

Portable definitions and skill-specific resources live in `skills/<name>/`; the
authored entrypoint is `SKILL.source.md`. `shared/references/` is the canonical
source for reused contracts and runtimes, and `shared/manifest.json` maps each
shared file to an exact build destination. `scripts/build_skills.py` stages
self-contained skills under `.build/skills` without writing generated copies
into the authored tree. Authored and built skill metadata has no version field.

The work-item family illustrates this materialization boundary.
`work-item-contract.md` and `work_item.py` are copied into `askme`, `goal`,
`task-prepare`, `task-review`, and `task-triage`;
`work-item-contract.schema.json` is copied into the same set except
`task-triage`. Each installed skill uses its own copies. The shared validator
returns the exact verdicts `ready`, `needs_clarification`, or `blocked`.
`task-triage` additionally receives a focused GitLab runner. It stores
content-addressed collection evidence and analysis below XDG state, reuses
per-issue analysis by source fingerprint, and atomically updates stable Markdown
reports without changing GitLab.
All three task skills receive one release-planning validator. Triage owns release
and milestone evidence, review validates the shared sidecar, and preparation
consumes current scoped triage instead of duplicating SemVer policy.

The authored repository is not a portable installation source and does not ship
a portable-skills CLI. Portable skills are installed from the GitHub Pages
distribution with the separately versioned `skills` CLI. The optional npm
package `@kisev/skills-opencode` provides the `skills-opencode` CLI for OpenCode
integration. It does not install, update, inspect, or remove portable skills;
their lifecycle belongs to the separate `skills` CLI.

`packages/skills/package.json` is the private version authority for the portable
distribution. `scripts/build_distribution.py` creates the Pages payload under
`.build/packages/skills`: well-known indexes, release metadata and locks, and
one content-addressed SHA-256 archive with root `SKILL.md` per skill. A release
manifest binds every Pages file and the exact npm tarball to the tag and source
revision. The tag workflow runs the full gate, publishes and verifies Pages and
npm, then creates the GitHub Release.

## Host Integration

Portable skills are host-neutral and every published archive is self-contained.
`packages/opencode/` is an optional OpenCode adapter and contains no copied
skills. Before `npm pack`, skill commands, the LSP catalog, and authored agent
and plugin assets are materialized under `packages/opencode/dist/assets/`.

The installer changes only the selected command, agent, and plugin assets after
a preview and matching `confirmation_digest`. Ownership manifests detect
collisions and preserve user drift. Canonical agent assets define prompts and
permissions; separate profile configuration defines models, variants, and
additional critics, while a semantic manifest records rendered hashes and the
package version. Selectable plugins are opt-in.

## OpenCode Runtime

The package exports one core infrastructure plugin and exactly three selectable
plugin modules: `rules-injector`, `rtk`, and `zed-bell`. The core plugin registers
only the `route` package tool. This package surface does not become a runtime
dependency of portable skills.

The direct CLI exposes the versioned, read-only `doctor` facts API. It inspects
configuration, LSP, ownership, and lifecycle state without
loading plugin factories, repairing state, or starting LSP servers. Missing host
facts are reported as `unavailable` or `incomplete`. The canonical
`shared/references/lsp-catalog.json` is materialized into the OpenCode package.

Package writes use bounded global or project roots, private locks and
confirmation receipts, final revalidation, atomic file replacement, and a
journaled rollback path. Stale, expired, superseded, or replayed confirmations
fail before mutation; user-owned files and unrelated durable state remain
outside package ownership. Scope-aware direct commands default to the current
directory; one `--global` flag selects global state. Direct CLI administration
uses the same project default. Portable cleanup belongs to the external `skills`
CLI and has no package-managed snapshots or rollback. Global archive state is shared globally; project archives are
isolated by project-root digest.

## Routing Contracts

The OpenCode `manager` owns the evidence -> plan -> authorization -> execution ->
checks -> report lifecycle for routed work. The `route` tool has four categories: `exploration` to
`mapper`, `architecture` to `architect`, `implementation` to `worker`, and
`review` to `review` or one selected `critic`. The manager delegates all substantive
work, including read-only quick requests, and routes write-capable documentation as implementation.
The `review` agent is available directly and as a subagent; it performs the primary
review and delegates independent passes to critics according to the selected skill.
It may fix project files only after an explicit user request and a visible transition
out of the read-only review phase.

Routing inventory comes from resolved host configuration; callers cannot inject
agents, capabilities, tools, models, or availability. A routing decision records
matrix and host-inventory revisions. Its one-use, TTL-bound receipt binds the
task, requirements, destination, agent, execution card, and expiry. Native Task
dispatch and result hooks validate the receipt, execution card, and structured
mapper, worker, review, or critic report. Execution cards bind writable and
forbidden paths, checks, explicit VCS operations, and separate execution,
publication, and history-rewrite confirmations.

## Build Invariants

- The JSON manifest maps canonical shared inputs only to declared build paths.
- Authored skill trees contain `SKILL.source.md`, no generated `SKILL.md`, and no
  committed manifest destinations.
- Authored and built skill frontmatter has no version field.
- `--check` validates isolated staging and reports artifact drift without
  changing authored files.
- The supported installer reads the well-known Pages index, verifies each
  archive digest, and runs no build command on the user's machine.
- Manifest paths are normalized, relative, and bounded to
  `shared/references/` and an existing skill; source, destination, and authored
  skill symlinks are rejected.
- Source remains unchanged, and build output is replaced only after complete
  staging and validation.
- Release checks bind the Pages version and source revision to the exact tag;
  publication promotes only preflighted artifacts and verifies both remote
  channels before creating the GitHub Release.
- Work-item findings have stable ordering and reports bind item and evidence
  digests, so unchanged checks produce the same verdict.
