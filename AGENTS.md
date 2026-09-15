# Repository Guidance

## General rules

### Language and style

- Reason and respond in the language of the latest user request; use English when it is ambiguous.
- Write code comments and commit messages in English.
- Write documentation and user-facing text in the language established by the repository; use English if no standard is explicit.
- Preserve the style, structure, and abstraction level used by analogous files in this repository.
- Be concise and critical: identify risks, disputed decisions, and strong alternatives.
- If user intent is unclear and an error could affect a release, compatibility, or security, ask one short clarifying question.

### Core engineering rules

- Deliver complete implementations without stubs.
- Before making changes, examine the minimum sufficient set of relevant files,
  including analogous implementations, tests, and documentation; expand the set
  for monorepos or multiple build systems.
- Start with this repository's rules and structure, then use its documentation.
- Do not invent branch, merge/pull-request, or deployment rules; take them from
  current repository configuration or canonical documentation.
- Do not duplicate existing utilities, templates, or logic blocks.
- Base change verification only on available facts.
- If data is insufficient, explicitly label the conclusion as an assumption.
- Do not make a finding without a clear risk, impact, or minimal remediation.
- Consider edge cases, security, input validation, compatibility, and performance.
- Remove unused code and do not complicate the solution unnecessarily.
- Add comments only when the code's purpose or constraint is not obvious.
- After changes, explicitly state completed and unrun checks.

### Document maintenance rules

- Keep the shared section as consistent as possible across repositories; put differences in the project section.
- Do not replace project rules with the shared template or remove user-specific clarifications without reason.
- Keep `AGENTS.md` compact.
- Add only rules that are genuinely applicable and verifiable in this repository.

## Project rules

- This repository publishes portable Agent Skills and an optional OpenCode npm integration; keep portable behavior independent of a checkout, provider, credential, user home, or team-specific configuration.
- Edit portable definitions under `skills/<name>/`; the authored entrypoint is `SKILL.source.md`.
- Edit shared contracts and runtimes only under `shared/references/`, and update `shared/manifest.json` when their materialization changes.
- Keep OpenCode-only commands, agents, plugins, routing, and installer behavior under `packages/opencode/`.
- Do not edit `.build/`, `packages/opencode/dist/`, generated `SKILL.md`, or copied assets directly; use `task generate` and verify reproducibility with `task generate:check`.
- Run `mise install` from the repository root before making changes.
- Treat `taskfile.yml` as the only task graph; workflows and hooks must call its public tasks instead of duplicating tool commands.
- Add focused contract or regression tests for observable behavior.
- Run `task format` after maintained-source formatting changes and `task check` before submitting a change.
- Run `task dependency:audit` when dependency metadata changes and before pushing through Lefthook.
- Preserve agentskills.io frontmatter constraints and keep every built skill self-contained.
- Keep Python runners shipped in portable skills compatible with Python 3.12+ and standard-library-only.
- Validate every committed `*.schema.json` with a concrete valid instance and add it to the exhaustive mapping in `tests/test_json_schemas.py`.
- Require preview, explicit confirmation, final revalidation, bounded paths, and atomic replacement or rollback for write-capable flows.
- Keep credentials, private endpoints, local paths, caches, live-eval output, and generated artifacts out of Git.
- Do not weaken a failing gate with exclusions, warning baselines, missing-import ignores, or skipped tests without a documented compatibility reason.
- Update `specs/` and `specs/traceability.json` for material behavior, compatibility, or security-boundary changes.
- For engineering-only commits with no specification impact, add `Spec-Impact: none - <reason>` to the commit message.
- Never rewrite published tags or package versions; use a new patch version for release-only corrections.
- Keep the portable version manifest, OpenCode package and lockfile, catalog, changelog heading, annotated `vX.Y.Z` tag, Pages distribution, npm artifact, and GitHub Release on one commit; `.github/workflows/publish.yml` owns preflight, publication, verification, and release creation.
