# Contributing to Agent Skills

[Русский](CONTRIBUTING.ru.md)

## Change Scope

Each `skills/` directory is an authored definition, not an installation
artifact. The build must turn every definition into a portable, self-contained
skill without a checkout, user home, particular provider, credentials, or one
team's configuration. OpenCode-specific agents, commands, and plugins belong
only in `packages/opencode/`.

Agree on a material behavior, compatibility, or security-boundary change before
implementing it. A new runner needs an observable contract: JSON on stdout,
diagnostics on stderr, defined exit codes, `--help`, `--capabilities`, and a
confirmed two-phase write when it changes files.

## Local Validation

Install pinned runtimes and standalone tools from the repository root:

```shell
mise install
task --list
```

`taskfile.yml` is the only task graph. Local development, Lefthook, and GitHub
Actions invoke its public tasks rather than duplicating tool commands. Run the
single quality gate before submitting any change:

```shell
task check
```

`format` may change the tracked checkout, while `task generate` writes only
ignored artifacts. Portable authored entrypoints are named `SKILL.source.md`;
`scripts/build_skills.py` writes `SKILL.md` and injects files declared by
`shared/manifest.json` only under `.build/skills`. OpenCode commands and the
copied LSP catalog are generated only into
`packages/opencode/dist/assets/` before packing; their sources are
`packages/opencode/src/registry.ts` and `shared/references/`.

`package:check` itself runs `npm ci`, Prettier, oxlint, tsc, Node tests,
generated-assets drift, smoke through pinned OpenCode, and the npm-pack
allowlist. An ordinary check does not need separate npm commands.
`dependency:audit` checks the locked Python and npm dependency graphs. Lefthook
runs it after the complete quality gate before push; it remains separate from
ordinary CI because it depends on live vulnerability services.

If an executable is missing, run `mise current` after installation. If
`uv run --locked` reports drift, deliberately change the pin in `pyproject.toml`
and then run `uv lock`; do not update dependencies implicitly. To reproduce a
package failure, run `task package:check` from the repository root.

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
- Reproduce package failures with `task package:check` at the repository root
  to retain the CI versions and order.

## Quality and Review

- Preserve frontmatter and agentskills.io format constraints for every
  `SKILL.source.md`; the built name is `SKILL.md`.
- Add focused tests for public contracts or meaningful regression risk.
- Never include credentials, tokens, internal endpoints, local paths, caches, or
  build artifacts in changes.

## Git Hooks

Install hooks after bootstrap:

```shell
lefthook install
```

`pre-commit` invokes `task pre-commit` and selects fast non-mutating checks by
staged and deleted paths, including schemas, specs, and toolchain metadata.
`pre-push` invokes full `task check` followed by `task dependency:audit`. Hooks
do not apply fixes or run `git add`.

Use English for code, comments, and commit messages; user documentation follows
the language of its existing section. Preserve machine tokens exactly.

Run live evaluations only explicitly with exact `--host`, `--model`, timeout,
token/cost limits, and output path. Do not add model defaults or live output to
Git; ordinary CI runs only the offline suite. Describe purpose, security impact,
checks run, and deliberately omitted checks in a pull request.

## Releases

Portable-skill versions are fixed in their metadata. The Pages distribution,
`@kisev/skills-opencode` version, tag, and GitHub Release must refer to one
commit. Do not change a published version: release a new patch version instead.
A tag push starts the single `.github/workflows/publish.yml` release workflow.
It runs the full quality gate before publishing, builds one exact npm tarball and
a cross-channel digest manifest, publishes and verifies Pages and npm, and only
then creates the GitHub Release. npm publishing uses trusted publishing through
OIDC and verifies the registry tarball, imports, CLI, signatures, and provenance.
