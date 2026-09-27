# Add or Rename an npm Workspace Package

[Русский](../ru/how-to/npm-package-lifecycle.md)

Use this guide to add, rename, or remove an npm workspace package. Every
package name participates in a complete publication graph: workspace wiring,
task graph, dev and release packaging, publish order, smoke tests, and
per-name npm trusted-publisher bindings. A name that misses any surface breaks
CI or the Publish workflow.

The contract test `test_every_workspace_package_is_wired_into_the_publication_graph`
in `tests/test_tooling_contracts.py` fails with a pointer to this page whenever
the root workspace list and the publication graph diverge.

## Rewire the Repository Graph

Update every surface for the new name, in dependency order (`@kisev/safe-fs`
before `@kisev/memomatic` and `@kisev/agentomatic`):

| Surface | What to update |
| - | - |
| `package.json` (root) | Exact `workspaces` list; pinned by contract tests |
| `package-lock.json` | Regenerate with `npm install` |
| `taskfile.yml` | `package:build` builds dependencies before consumers; `typecheck:typescript` must keep `deps: [package:build]` |
| `scripts/build_dev_artifacts.py` | `members` tuple in dependency order; dev dependency pinning is derived automatically |
| `scripts/build_release_artifacts.py` | `PACKAGE_MEMBERS` in the same order |
| `scripts/publish_npm_release.py` | `NPM_PUBLISH_ORDER` and the `registry_smoke` expectations |
| `packages/agentomatic/test/smoke.mjs` | Tarball environment variables and the install list |
| `tests/test_tooling_contracts.py` | Workspaces pin and build-order assertions |
| `tests/test_release_contract.py` | Manifest member entries |

Dependency declarations between workspace packages use `^` ranges in source
`package.json` files; dev tarball packing rewrites them to exact dev versions,
so clean checkouts and registry installs never fall back to the npm registry.

## Meet the CLI Contract

Every package with a `bin` entry must support:

- `--version`: print exactly the installed `package.json` version, create no
  state directories, and touch no XDG locations.
- `--help`: exit 0.

The contract is enforced twice: by `smoke.mjs` in the local `task check` gate
and by `registry_smoke` after publication. A CLI that fails `--version` fails
the Publish workflow minutes after a successful upload.

## Bootstrap a New Package Name on npm

Trusted publishing is bound per existing package name in the package settings;
an OIDC workflow cannot create a new name, and pre-registration is not
available. Bootstrap each new name once from the terminal:

```shell
npm --version          # npm 11.15.0 or newer
npm logout
npm login --auth-type=web

# Download the exact validated tarballs from the producing Publish run
gh run download <run-id> -n npm-dev-<run-id>-1 -D .build/release

# Publish in dependency order, then bind the trusted publisher
npm publish .build/release/safe-fs.tgz   --tag dev --access public
npm publish .build/release/memomatic.tgz --tag dev --access public
npm publish .build/release/package.tgz   --tag dev --access public

# npm never allows deleting `latest`; retarget it to a published version
npm dist-tag add @kisev/safe-fs@<newest-dev-version> latest    # no stable release yet
npm dist-tag add @kisev/memomatic@<newest-dev-version> latest  # no stable release yet
npm dist-tag add @kisev/agentomatic@<stable-version> latest    # name with a stable release

npm trust github @kisev/safe-fs    --repo kisev/skills --file publish.yml --allow-publish --yes
npm trust github @kisev/memomatic --repo kisev/skills --file publish.yml --allow-publish --yes
npm trust github @kisev/agentomatic --repo kisev/skills --file publish.yml --allow-publish --yes
```

The first `npm trust` requires 2FA; the browser offers a five-minute skip for
the remaining names. The next push to `dev` publishes through OIDC.

Finish the bootstrap by verifying that every `latest` tag references the newest
intended version and never an old prerelease:

```shell
npm dist-tag ls @kisev/agentomatic
npm dist-tag ls @kisev/safe-fs
npm dist-tag ls @kisev/memomatic
```

Traps:

- Versions published from a local terminal carry no provenance attestation.
  Never rerun a Publish run that covers locally published versions; the
  provenance verification fails by design. Let the next push supersede them.
- npm assigns the `latest` dist-tag to the first published dev version of a
  new name, and a local publish of an existing name moves `latest` whenever
  the published dev version is semver-greater than the current `latest`.
- npm does not allow deleting `latest` (the registry rejects
  `npm dist-tag rm <name> latest` with 400; see npm/cli#8490). Until a name
  has a stable release, keep `latest` retargeted to the newest dev version;
  once a stable release exists, the publication gate fails if `latest` still
  references a prerelease.
- Brand-new names propagate slowly: CDN negative caching can consume the
  shared ten-minute wait budget on metadata and tarball verification. Once the
  versions answer 200 on the registry, rerun only the failed jobs with the
  retained artifacts: `gh run rerun <run-id> --failed`.
- Development versions embed a 12-hex short revision (`…dev.48.gf6e4f0e086aa`).
  Query exact version endpoints, and prefer `npm view --prefer-online` to
  bypass the cached negative responses.

## Rename an Existing Package

A rename is an add plus a retirement:

1. Bootstrap the new name as above.
2. Rewire the repository graph and migrate runtime state and installer
   references in the same change.
3. Deprecate the old name; never unpublish or move released versions or tags:

```shell
npm deprecate @kisev/old-name@* "Renamed to @kisev/new-name"
```
