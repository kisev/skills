# Architecture

## Source of truth

Portable skills live under `skills/<name>/` and are complete installation
units. A skill may use only files below its own root at runtime. `shared/` is
maintainer input, never an installed runtime dependency. `scripts/sync_shared.py`
materializes exact copies from the manifest and committed copies are checked in
under each skill.

The repository has no user-facing CLI. Maintainer scripts may be Python
stdlib-only; Python runners, when a skill needs them, belong to that skill.

## Host integration

Portable skills describe intent without requiring a particular host. A host
may provide its normal interactive question facility; if it cannot, the agent
asks in chat. OpenCode-only adapters and future agents/plugins belong in the
optional `packages/opencode/` package and are not required to install or run a
portable skill.

## Materialization invariants

- The JSON manifest is the only mapping from shared sources to skill paths.
- Paths are relative, normalized, and confined to `shared/references/` and
  `skills/` respectively.
- Symlinks are rejected in source and destination paths.
- Normalization and all source reads happen before writes.
- Staged files are replaced atomically, with rollback on replacement failure.
- `--check` is read-only and reports drift through a non-zero exit status.
