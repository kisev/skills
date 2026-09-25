# Contributing to Agent Skills

[Русский](CONTRIBUTING.ru.md)

## Change Scope

Each directory under `skills/` is an authored definition, not an installation
artifact. The build must turn every definition into a portable, self-contained
skill without depending on a checkout, user home, particular provider,
credentials, or one team's configuration. OpenCode-specific agents, commands,
and plugins belong only in `packages/opencode/`.

Agree on a material behavior, compatibility, or security-boundary change before
implementing it. A new runner needs an observable contract: JSON on `stdout`,
diagnostics on `stderr`, defined exit codes, `--help`, and `--capabilities`.
Use the [shared interaction contract](shared/references/interaction-contract.md)
to classify writes: bounded project-file edits are direct; external publication,
user configuration, destructive cleanup, history changes, releases, and package
lifecycle mutations require exact preview and confirmation.

## Local Validation

Install pinned runtimes and standalone tools from the repository root:

```shell
mise install
task install
task --list
```

`taskfile.yml` is the full repository and CI task graph. Lefthook directly runs
pinned tools only for its staged-file pre-commit fast path; pre-push and GitHub
Actions invoke public tasks. Run the single quality gate before submitting any
change:

```shell
task check
```

The main public tasks divide the checks as follows:

| Task | Purpose |
| - | - |
| `install` | Install pinned tools, locked dependencies, and Git hooks. |
| `tools` | Show the active pinned toolchain. |
| `format` | Format maintained source files. |
| `lint`, `typecheck`, `test` | Run source, formatting, type, and test checks. |
| `generate`, `generate:check` | Build ignored artifacts or check their reproducibility. |
| `skills:validate` | Run Agnix and `agentskills` validation. |
| `package:check` | Verify the complete OpenCode package lifecycle. |
| `eval:check` | Validate evaluation data and run the hostless offline suite. |
| `dependency:audit` | Audit the locked Python and npm dependency graphs. |
| `security` | Scan Git history and the working tree for secrets with gitleaks. |
| `check` | Run the complete local and CI quality gate. |
| `pre-push` | Run the complete local push gate used by Lefthook. |

`task format` may change tracked files, while `task generate` writes only
ignored artifacts. Portable authored entrypoints are named `SKILL.source.md`;
`scripts/build_skills.py` writes `SKILL.md` and injects files declared by
`shared/manifest.json` only under `.build/skills`. OpenCode commands and the
copied LSP catalog are generated only into `packages/opencode/dist/assets/`
before packing; their sources are `packages/opencode/src/registry.ts` and
`shared/references/`.

`package:check` installs locked npm dependencies, builds the package once, runs
Node.js tests, performs a smoke test through pinned OpenCode, and checks the npm
pack allowlist. Root lint and type-check tasks own the corresponding source
checks, so the package lifecycle does not repeat them.

`dependency:audit` checks the locked Python and npm dependency graphs.
`task pre-push` runs it concurrently with `task check`; it remains separate from
ordinary CI because it depends on live vulnerability services.

## Diagnostics

- If an executable is unavailable, run `mise install` and inspect versions with
  `mise current`.
- If `uv run --locked` reports drift, deliberately update the pin in
  `pyproject.toml`, then run `uv lock`; do not update dependencies implicitly.
- If `generate:check` reports drift, fix the canonical source and run
  `task generate`; never edit a build artifact directly.
- Agnix errors block validation. Existing warnings are printed and recorded in
  `.agnix-warnings.json`; a new warning also blocks the gate until fixed or its
  baseline is deliberately updated.
- Reproduce package failures with `task package:check` at the repository root to
  retain the CI versions and order.

## Quality and Review

- Preserve frontmatter and agentskills.io format constraints for every
  `SKILL.source.md`; the built name is `SKILL.md`, and neither authored nor built
  skill metadata carries a version.
- Add focused tests for public contracts or meaningful regression risk, not
  implementation details.
- Never include credentials, tokens, internal endpoints, local paths, caches,
  live-evaluation output, or build artifacts in changes.
- Run live evaluations only explicitly with exact `--host`, `--model`,
  `--timeout`, `--max-tokens`, `--max-cost`, and `--output` values. Do not add
  model defaults or live output to Git; ordinary CI runs only the offline suite.
- Describe the purpose, security impact, checks run, and deliberately omitted
  checks in a pull request.
- Use English for code, comments, and commit messages; user documentation
  follows the language of its existing section. Preserve machine tokens exactly.

## Git Hooks

Install hooks after bootstrap:

```shell
lefthook install
```

`pre-commit` runs fast, non-mutating lint and security checks directly against
staged files with pinned Mise tools. Deleted paths are excluded; builds, tests,
generation, and release checks do not run.

`pre-push` invokes `task pre-push`, which runs `task check` and
`task dependency:audit` concurrently. The full gate runs the package lifecycle
once, without separate package type checking, testing, or generation before
`package:check`. Hooks do not apply fixes or run `git add`.

## Releases

Portable skills carry no version. Release identity belongs to the GitHub Pages
distribution metadata and each content-addressed archive digest. The GitHub
Pages distribution, `@kisev/skills-opencode` version, tag, and GitHub Release
must refer to one commit. Do not change a published version; publish a new patch
release instead.

Use `dev` as the integration branch. Direct commits and pull requests from
feature or fix branches may target `dev`. Pull requests into `main` must use
`dev` as their source and a merge commit. Prepare the maintainer-selected stable
version and both changelogs on `dev`; merging does not itself publish a release.

Invoke the project `project-release` skill to run the guarded release workflow.
It requires separate confirmation before pushing `dev`, merging into `main`,
creating the annotated `vX.Y.Z` tag, and pushing that tag. The tag must reference
the resulting `main` merge commit.

The tag starts `.github/workflows/publish.yml`. It revalidates the published tag
and revision, builds one exact npm tarball and cross-channel digest manifest,
publishes and verifies stable GitHub Pages and npm `latest`, and only then creates
the GitHub Release. npm publishing uses trusted publishing through OIDC and
verifies the registry tarball, imports, CLI, signatures, and provenance.

For every push to `dev`, the same workflow runs the complete gate, then replaces
only the Pages `/dev` channel and publishes a unique npm prerelease under dist-tag
`dev`. Development snapshots do not choose a stable SemVer and create no GitHub
Release.
