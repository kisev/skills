# Architecture

[Русский](ru/architecture.md)

## Source of Truth

Portable skills in `skills/<name>/` are self-contained. `shared/` is maintainer
input, not an installed runtime dependency. `scripts/build_skills.py` writes
exact copies only to ignored `.build/skills`.

Shared English contracts are materialized from `shared/references/`; schemas
and `work_item.py` remain canonical machine inputs. In particular,
`shared/references/work-item-contract.schema.json` is materialized for
`task-prepare` and `task-review`; its validator can return
`needs_clarification`. Installed skills never read `shared/`.

`packages/skills/package.json` defines the build-only `@kisev/skills`
distribution. `scripts/build_distribution.py` produces
`.build/packages/skills` archives with root `SKILL.md`, SHA-256 locks and the
source revision; this is the boundary before `npm pack`.

## Host Integration

Portable skills are host-neutral. `packages/opencode/` is optional and contains
OpenCode-specific assets only.

## OpenCode Runtime

Materialized runners use only their own files and XDG state. Package tools do
not make portable skills depend on the checkout. The canonical checkout is
`/home/kisev/Projects/Github/kisev/skills`, package assets are materialized in
`packages/opencode/dist/assets`, and unavailable host facts are explicitly
`unavailable/incomplete`. The optional `agent_profiles` adapter does not change
those boundaries.

## Build Invariants

- The JSON manifest maps machine inputs to build paths.
- `--check` reports artifact drift without changing source files.
