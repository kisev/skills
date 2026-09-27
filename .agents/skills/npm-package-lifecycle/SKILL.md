---
name: npm-package-lifecycle
description: Use when adding, renaming, or removing an npm workspace package in this repository, or when a Publish workflow fails on a package name that is new to the npm registry. Covers repository graph rewiring and the npm trusted-publisher bootstrap.
---

# npm Package Lifecycle

Add, rename, or remove an npm workspace package without breaking the
publication graph. The full runbook is
`docs/how-to/npm-package-lifecycle.md` (Russian mirror in `docs/ru/how-to/`);
this skill holds the traps that must not be rediscovered.

## Preconditions

- Confirm the change type: add, rename, or remove.
- Expect `tests/test_tooling_contracts.py` to fail until every graph surface
  lists the new name; the failing assertion is the checklist pointer.
- Never unpublish or move released npm versions, dist-tags, or git tags.

## Repository Wiring

Every workspace package name must appear, in dependency order
(`safe-fs` before its consumers), on all surfaces: root `workspaces`,
`package:build` in `taskfile.yml` (with `typecheck:typescript` depending on
`package:build`), `members` in `scripts/build_dev_artifacts.py`,
`PACKAGE_MEMBERS` in `scripts/build_release_artifacts.py`,
`NPM_PUBLISH_ORDER` plus `registry_smoke` in `scripts/publish_npm_release.py`,
the tarball environment map in `packages/agentomatic/test/smoke.mjs`, and the
contract tests. A package with a `bin` must answer `--version` with its exact
installed version and `--help` with exit 0, creating no state.

## npm Bootstrap for a New Name

Trusted publishing binds per existing package name; OIDC cannot create a new
name and pre-registration is unavailable. Bootstrap from the terminal:
`npm login --auth-type=web`, download the exact tarballs with
`gh run download <run-id> -n npm-dev-<run-id>-1 -D .build/release`, publish in
dependency order with `--tag dev --access public`, then
`npm trust github <name> --repo kisev/skills --file publish.yml --allow-publish --yes`
for each name. The next `dev` push publishes through OIDC.

## Traps

- Locally published versions carry no provenance. Never rerun a Publish run
  covering them; verification fails by design and the next push supersedes.
- npm sets `latest` to the first published dev version; run
  `npm dist-tag rm <name> latest` until the first stable release.
- New names propagate slowly through the CDN: a failed Publish run is rerun
  with `gh run rerun <run-id> --failed` only after the exact versions answer
  200 on the registry. Dev versions embed a 12-hex short revision.
- A rename must deprecate the old name
  (`npm deprecate @kisev/old@* "Renamed to @kisev/new"`) and migrate runtime
  state and installer references in the same change.
