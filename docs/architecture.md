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
distribution with `skillmate`, the installer-configurator delivered on PyPI, or
with the compatible `skills` CLI (`npx --yes skills@latest`). `skillmate` places
each selected skill per host, lays out command surfaces, and owns the
preview-confirm safety model; the `skills` channel installs portable skills
into `.agents/skills` and is kept compatible.

`packages/skills/package.json` is the private version authority for the portable
distribution. `scripts/build_distribution.py` creates the Pages payload under
`.build/packages/skills`: well-known indexes, release metadata and locks, and
one content-addressed SHA-256 archive with root `SKILL.md` per skill. A release
manifest binds every Pages file to the tag, version, channel, and source
revision. The tag workflow runs the full gate, publishes and verifies Pages,
uploads `skillmate` to PyPI from `main` tags through trusted publishing, then
creates the GitHub Release.

A push to `dev` invokes the same publication workflow without a stable tag and
runs the complete gate. It then derives a technical prerelease version and
replaces only Pages `/dev`; the dev channel never reaches a package registry.
Each Pages deployment composes the stable root and `/dev` so either channel
preserves the other.

## Host Integration

Portable skills are host-neutral and every published archive is self-contained.
`apps/skillmate/` is the installer-configurator and adapter registry. It
materializes each selected skill per host: Codex reads `.agents/skills/` and
spells skill references `$name`, Claude reads `.claude/skills/` with command
surfaces under `.claude/commands/`, and OpenCode reads `.opencode/skills/`
(with `~/.config/opencode/` as the global root) with command surfaces under
`.opencode/commands/`. Adapters are declarative; adding a host adds no runtime
dependency for portable skills.

Every write path goes through one plan: a preview of all changes, explicit
confirmation, and ownership manifests under `.skillmate/` that detect
collisions with foreign files and preserve user drift. A file modified after
installation is never silently overwritten, and removing it requires an
explicit `--confirm-drift`.

## skillmate Runtime

`skillmate` is a standard-library-only Python 3.12+ application. The
distribution module resolves the versioned Pages index, verifies each archive
digest, and extracts without fallbacks; `--from-checkout` runs the checkout's
own distribution build and stamps the installation as dev. The CLI offers
`install`, `update`, `remove`, `doctor`, and `status`; every mutating command
previews a versioned plan document and writes only after explicit
confirmation, while `doctor` and `status` are read-only. OpenCode
configuration fragments are edited with comment-preserving splices that stay
byte-identical when repeated, and conflicts are reported, never merged.

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
  publication promotes only preflighted artifacts and verifies the deployed
  Pages artifact before creating the GitHub Release.
- Development publication runs the complete gate for a `dev` push, verifies its
  exact Pages artifact, and cannot update the stable Pages root.
- Work-item findings have stable ordering and reports bind item and evidence
  digests, so unchanged checks produce the same verdict.
