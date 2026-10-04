# Contributing to Agent Skills

[Русский](CONTRIBUTING.ru.md)

## Change Scope

Each directory under `skills/` is an authored definition, not an installation
artifact. The build must turn every definition into a portable, self-contained
skill without depending on a checkout, user home, particular provider,
credentials, or one team's configuration. OpenCode-specific agents, commands,
and plugins belong only in `packages/agentomatic/`.

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
| `gates:check` | Fail when a rendered gate copy drifts from `gate-registry.json`. |
| `check:core` | Run the always-on core shared by every push gate. |
| `check` | Run the complete local and CI quality gate. |
| `pre-push` | Run the complete unscoped local gate for manual and release use. |

`task format` may change tracked files, while `task generate` writes only
ignored artifacts. Portable authored entrypoints are named `SKILL.source.md`;
`scripts/build_skills.py` writes `SKILL.md` and injects files declared by
`shared/manifest.json` only under `.build/skills`. OpenCode commands and the
copied LSP catalog are generated only into `packages/agentomatic/dist/assets/`
before packing; their sources are `packages/agentomatic/src/registry.ts` and
`shared/references/`.

`package:check` installs locked npm dependencies, builds the package once, runs
Node.js tests, performs a smoke test through pinned OpenCode, and checks the npm
pack allowlist. Root lint and type-check tasks own the corresponding source
checks, so the package lifecycle does not repeat them.

`dependency:audit` checks the locked Python and npm dependency graphs and
belongs to `check:core`, so every full local gate and the CI matrix run it.
It queries live vulnerability services over the network while doing so.

`gate-registry.json` is the single source for gate composition: one entry per
layer maps input paths to a gate task. `scripts/generate_gates.py` renders the
CI `matrix.include` blocks and the Lefthook pre-push glob lists from the
registry; branch policy, job skeletons, aggregation, and task calls stay
hand-written. `task gates:check` runs in `check:core` and in CI and fails when
a rendered copy, the task graph, or a skeleton drifts from the registry; after
editing the registry, run `task gates:write`.

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

`pre-push` scopes its jobs to the push delta: the delta resolves against the
branch upstream and falls back to every tracked file when there is none, so
first pushes run the complete gate. The always-on job runs `task check:core`,
which includes the documentation, docs-site, and dependency-audit layers;
`task test:python` and `task package:check` run only when the delta touches
their stack inputs, and every scoped glob list carries the meta triggers, so
tooling edits run every layer. CI reruns the complete gate on every push, so
scoping never reduces verification, and `task pre-push` remains the unscoped
gate for manual diagnosis and releases. Hooks do not apply fixes or run
`git add`.

## Releases

Portable skills carry no version. Release identity belongs to the GitHub Pages
distribution metadata and each content-addressed archive digest. The GitHub
Pages distribution, `@kisev/agentomatic` version, tag, and GitHub Release
must refer to one commit. Do not change a published version; publish a new patch
release instead.

Use `dev` as the integration trunk. Commit to `dev` directly by default and
open feature or fix pull requests into `dev` only when a branch helps. `main`
changes only through pull requests with a merge commit and tracks the latest
stable feature line. Prepare the maintainer-selected stable version and both
changelogs on `dev`; when the release point is not `dev` head, cut a release
prep branch at the selected commit and prepare there. Merging does not itself
publish a release.

A feature release `X.Y.0` ships through a pull request into `main` and is tagged
on the resulting merge commit. A patch to the latest feature line `X.Y.z` ships
the same way from `dev` or a `fix/*` branch. When the next feature release
ships, cut `release/vX.Y` from the previous line's latest tag and bring the
publication automation in that branch up to date: tag pushes run
`.github/workflows/publish.yml` from the tagged commit, so a stale workflow
would publish an old-line patch as `latest`. Patch an older line through a
`fix/*` pull request into `release/vX.Y` and tag its merge commit.

Invoke the project `project-release` skill to run the guarded release workflow.
It requires separate confirmation before pushing the release branch, merging
into `main`, creating the annotated `vX.Y.Z` tag, and pushing that tag. The tag
must reference the resulting merge commit.

The tag starts `.github/workflows/publish.yml`. It revalidates the published tag
and revision, resolves the publication channel from the tagged commit, builds
exact npm tarballs for every workspace publication member and a cross-channel
digest manifest, then publishes and verifies npm `latest` with the stable GitHub
Pages root for a commit on `main`, or the npm `vX.Y` dist-tag without touching
Pages for a commit on `release/vX.Y`, and only then creates the GitHub Release.
npm publishing uses trusted publishing through OIDC and verifies the registry
tarball, imports, CLI, signatures, and provenance.

The manifest records `@kisev/safe-fs`, `@kisev/memomatic`, and `@kisev/agentomatic`
with their own versions and exact dependency pins. Every member must finish
publication and verification before the workflow declares success.

For every push to `dev`, CI runs the complete gate on the pushed revision, and
the publication workflow waits for its terminal `success` conclusion for the
same revision before it rebuilds the exact artifacts, replaces only the Pages
`/dev` channel, and publishes a unique npm prerelease under dist-tag `dev`. If
that run failed, was cancelled by a newer push, or is missing, the publication
stops. Development snapshots do not choose a stable SemVer and create no GitHub
Release.
