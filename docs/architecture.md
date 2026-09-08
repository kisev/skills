# Architecture

[Русский](ru/architecture.md)

## Source of Truth

Portable skills in `skills/<name>/` are self-contained. `shared/` is maintainer
input, not an installed runtime dependency. `scripts/build_skills.py` writes
exact copies only to ignored `.build/skills`.

The canonical maintainer checkout is `/home/kisev/Projects/Github/kisev/skills`;
other local copies are neither installation nor change sources. The repository
has no user CLI. Maintainer scripts use Python standard library only, while a
skill runner belongs inside its owning skill.

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
OpenCode-specific assets only; it does not contain copied skills. OpenCode
commands, the LSP catalog, and authored agent/plugin assets are materialized to
`packages/opencode/dist/assets/` before `npm pack`. Its installer applies those
assets only after dry-run and a matching digest, preserving user drift through
ownership manifests. Agent assets hold prompts and permissions; profile
configuration holds models, variants, and additional critics. Stateful plugins
are opt-in and create no state, timers, sessions, or mutations while disabled.

## OpenCode Runtime

Materialized runners use only their own files and XDG state. Package tools do
not make portable skills depend on the checkout. The canonical checkout is
`/home/kisev/Projects/Github/kisev/skills`, package assets are materialized in
`packages/opencode/dist/assets`, and unavailable host facts are explicitly
`unavailable/incomplete`. The optional `agent_profiles` adapter does not change
those boundaries. Specialized Python-runner skills remain ordinary self-contained
Agent Skills; `goal` is a read-only prompt-only adapter. `doctor` shares a
versioned read-only facts API with the direct CLI and never invokes plugin
factories, lifecycle recovery, receipts, journals, or LSP servers. Routing and
mutation receipts are private, one-time, TTL-bound, and reject stale or replayed
inputs. Stateful records use private atomic writes and locks; incomplete
background attempts become `orphaned` on reload.

## Build Invariants

- The JSON manifest maps machine inputs to build paths.
- `--check` reports artifact drift without changing source files.
- Paths are normalized, relative, and constrained to the shared references and
  isolated output; source and destination symlinks are rejected.
- Source is unchanged and output is replaced only after complete staging.
- Work-item findings have stable sort order and bind reports to item/evidence
  digests, so unchanged checks produce the same verdict.
