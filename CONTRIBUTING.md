# Contributing to Agent Skills

[Русский](CONTRIBUTING.ru.md)

## Change Scope

Keep every `skills/` directory portable and self-contained. Do not add a
dependency on a checkout, user home, a particular provider, credentials, or one
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

Only `format` changes the tracked checkout. When shared references change, edit
the canonical file under `shared/references/` first, then run `task generate`;
portable copies are created only in ignored build artifacts. OpenCode commands
and the copied LSP catalog are generated only into
`packages/opencode/dist/assets/` before packing; their sources are
`packages/opencode/src/registry.ts` and `shared/references/`.

`package:check` itself runs `npm ci`, Prettier, oxlint, tsc, Node tests,
generated-assets drift, smoke through pinned OpenCode, and the npm-pack
allowlist. An ordinary check does not need separate npm commands.

If an executable is missing, run `mise current` after installation. If
`uv run --locked` reports drift, deliberately change the pin in `pyproject.toml`
and then run `uv lock`; do not update dependencies implicitly. To reproduce a
package failure, run `task package:check` from the repository root.

## Git Hooks

Install hooks after bootstrap:

```shell
lefthook install
```

`pre-commit` invokes `task pre-commit` and selects fast non-mutating checks by
staged paths. `pre-push` invokes full `task check`. Hooks do not apply fixes or
run `git add`.

Use English for canonical source, code, comments, commands, and commit messages.
Preserve machine tokens exactly and add focused tests for public contracts or
meaningful regression risks.

Run live evaluations only explicitly with exact `--host`, `--model`, timeout,
token/cost limits, and output path. Do not add model defaults or live output to
Git; ordinary CI runs only the offline suite. Describe the purpose, security
impact, checks run, and deliberately omitted checks in a pull request.

## Releases

Portable-skill versions are fixed in their metadata. The
`@kisev/skills-opencode` version, tag, and GitHub Release must refer to one
commit. Do not change a published version: release a new patch version instead.
The npm package is published only by a tag push through
`.github/workflows/publish.yml`; the workflow checks the tag against the package
version and uses npm trusted publishing through OIDC. v1.0.0 is a one-time
interactive bootstrap before the package relationship exists.
