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

- This repository publishes portable Agent Skills, the `@kisev/agentomatic` npm integration with its workspace packages, and user-run applications under `apps/`; keep portable behavior independent of a checkout, provider, credential, user home, or team-specific configuration.
- Edit portable definitions under `skills/<name>/`; the authored entrypoint is `SKILL.source.md`.
- Edit shared contracts and runtimes only under `shared/references/`, and update `shared/manifest.json` when their materialization changes.
- Keep OpenCode-only commands, agents, plugins, routing, and installer behavior under `packages/agentomatic/`, npm-publishable shared packages under `packages/`, and user-run cross-host applications (any stack) under `apps/<name>/`.
- The sole reviewmatic runtime is Python in `apps/reviewmatic/`; its `src/reviewmatic/portable/` tree is materialized from `shared/manifest.json` (`pythonRuntime`). Never edit that tree by hand: change the canon, run `task generate`, and verify with `task generate:check`. Golden fixtures are frozen from TypeScript revision `3e409c217e94d643f77eb543caab9a2ed4b7288d` and asserted by Python tests; do not regenerate expected values from the Python implementation.
- Adding, renaming, or removing a workspace npm package rewires the complete publication graph and npm trusted-publisher bindings; follow `docs/how-to/npm-package-lifecycle.md` and the `npm-package-lifecycle` project skill before pushing.
- Do not edit `.build/`, `packages/agentomatic/dist/`, generated `SKILL.md`, or copied assets directly; use `task generate` and verify reproducibility with `task generate:check`.
- Run `mise install` from the repository root before making changes.
- Treat `taskfile.yml` as the full repository and CI task graph; the Lefthook pre-commit fast path may invoke pinned Mise tools directly for staged files, while workflows and pre-push must call public tasks.
- Add focused contract or regression tests for observable behavior.
- Run `task format` after maintained-source formatting changes; run `task check` before a non-push handoff, while Lefthook `pre-push` owns local verification for pushes.
- Treat the Lefthook `pre-push` jobs as the scoped local push gate: hook-level `files:` resolves the push delta against the branch upstream and falls back to all tracked files when there is none, so first pushes run the complete gate; `task check:core` always runs, while `task test:python` and `task package:check` run only when the delta touches their stack inputs. `gate-registry.json` is the single source for gate composition: `scripts/generate_gates.py` renders the CI `matrix.include` blocks and the pre-push glob lists, and `task gates:check` fails every gate when a rendered copy, the task graph, or a workflow skeleton drifts from it. CI reruns the complete gate on every push, so scoping never reduces verification. Use `task pre-push` for the unscoped manual or release gate, and do not run gate tasks immediately before a push unless diagnosing a failure.
- Preserve agentskills.io frontmatter constraints; every built skill archive stays self-contained, and cross-skill relations are declared only in `shared/skill-relations.json` (`requires`/`uses`/`recommends`) and materialized into built `SKILL.md` as a recommendational "Related skills" section, never as a runtime import of another archive.
- Keep Python runners executed inside portable skill archives compatible with Python 3.12+ and standard-library-only; user-installed applications under `apps/` may declare dependencies.
- Validate every committed `*.schema.json` with a concrete valid instance and add it to the exhaustive mapping in `tests/test_json_schemas.py`.
- Write ordinary project files directly with bounded paths and atomic replacement or rollback; require preview and explicit confirmation only for external publication, user configuration, destructive cleanup, history changes, releases, and package lifecycle mutations.
- When `skill-doctor` is explicitly invoked in this repository, search the XDG skill-doctor state for applicable diagnoses, including diagnoses recorded in other working projects, and match them against the current `skills/` sources through the skill's bundled runner; report which problems remain relevant, are fixed, or need clarification. A matching skill name alone is insufficient when the skill's recorded origin is ambiguous. The ordinary result is analysis and proposals; doctor does not modify skill sources.
- Keep credentials, private endpoints, local paths, caches, live-eval output, and generated artifacts out of Git.
- Do not weaken a failing gate with exclusions, warning baselines, missing-import ignores, or skipped tests without a documented compatibility reason.
- Never rewrite published tags or package versions; registry propagation alone is not a reason to bump: `task release:npm` waits up to 10 minutes, then inspect the failure and use `gh run rerun <run-id> --failed` with retained artifacts for transient failures; use a new patch only for actual release corrections.
- `dev` is the integration trunk: direct commits by default, feature/fix branches and pull requests into `dev` optional. `main` changes only through pull requests with a merge commit — feature releases from `dev` or a release prep branch cut at the selected commit, latest-line patches from `dev` or `fix/*`.
- Never commit with skipped hooks (`git commit --no-verify` or equivalents); if a hook fails on a legitimate change, fix the hook configuration and include the fix in the same change.
- Never create unsigned commits: keep `commit.gpgsign` enabled so every commit carries a signature; if signing fails, stop and fix the signing setup instead of committing without it.
- Keep the portable version manifest, OpenCode package and lockfile, changelog heading, annotated `vX.Y.Z` tag, Pages distribution, npm artifact, and GitHub Release aligned. Require explicit confirmation before merging into `main` and again before creating and pushing the annotated tag, with no publication run active or pending; `.github/workflows/publish.yml` publishes a `main` tag as npm `latest` plus the Pages root and a `release/vX.Y` tag as the npm `vX.Y` dist-tag without Pages; the dev channel awaits the terminal CI success of the same revision and refuses to publish when that run was cancelled, failed, or missing. Cut `release/vX.Y` from the previous line when a feature release ships and sync the publication automation into it, because tag pushes run the workflow from the tagged commit.
