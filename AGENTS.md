# Repository Guidance

## Scope

This repository publishes portable Agent Skills and an optional OpenCode npm integration. Keep portable behavior independent of a checkout, provider, credential, user home, or team-specific configuration.

## Sources And Generated Files

- Edit portable definitions under `skills/<name>/`; the authored entrypoint is `SKILL.source.md`.
- Edit shared contracts and runtimes only under `shared/references/` and update `shared/manifest.json` when their materialization changes.
- Edit OpenCode-only commands, agents, plugins, routing, and installer behavior only under `packages/opencode/`.
- Do not edit `.build/`, `packages/opencode/dist/`, generated `SKILL.md` files, or copied assets directly.
- Use `task generate` to produce ignored artifacts and `task generate:check` to verify reproducibility.

## Required Workflow

1. Run `mise install` from the repository root.
2. Make the smallest change that preserves the source/build/package boundaries.
3. Add focused contract or regression tests for observable behavior.
4. Run `task format` after maintained-source formatting changes.
5. Run `task check` before submitting a change.
6. Run `task dependency:audit` when dependency metadata changes and before pushing through Lefthook.

`taskfile.yml` is the only task graph. Workflows and hooks must call its public tasks instead of duplicating tool commands.

## Contracts And Safety

- Preserve agentskills.io frontmatter constraints and keep every built skill self-contained.
- Python runners shipped in portable skills must remain Python 3.12+ standard-library-only.
- Validate every committed `*.schema.json` with a concrete valid instance; add the schema to the exhaustive mapping in `tests/test_json_schemas.py`.
- Write-capable flows require preview, explicit confirmation, final revalidation, bounded paths, and atomic replacement or rollback.
- Keep credentials, private endpoints, local paths, caches, live-eval output, and generated artifacts out of Git.
- Do not weaken a failing gate with exclusions, warning baselines, missing-import ignores, or skipped tests unless the repository documents a concrete compatibility reason.

## Specifications And Commits

- Update `specs/` and `specs/traceability.json` for material behavior, compatibility, or security-boundary changes.
- For engineering-only commits with no specification impact, add `Spec-Impact: none - <reason>` to the commit message.
- Use English for code, comments, and commit messages. Follow the language of an existing user-documentation section.
- Never rewrite published tags or package versions. Release a new patch version for release-only corrections.

## Releases

The portable version manifest, OpenCode package and lockfile, catalog, changelog heading, annotated `vX.Y.Z` tag, Pages distribution, npm artifact, and GitHub Release must identify one commit. `.github/workflows/publish.yml` owns the complete release: full preflight, exact artifact construction, Pages and npm publication, post-publication verification, then GitHub Release creation.
