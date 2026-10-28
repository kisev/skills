# Publishing the `skillmate` Package

[Русский](../ru/how-to/pypi-package-lifecycle.md)

`skillmate` is this repository's single publication channel: the PyPI
distribution `skillmate`, owned by the `kisev` account. This document is the
complete lifecycle description — adding, versioning, publishing, and retiring
— and it describes exactly one channel. Nothing else in the repository
publishes to a package registry.

## Identity and Layout

- Distribution, import package, and console command are all `skillmate`.
- Source of truth: `apps/skillmate/` (hatchling src layout, Python 3.12+).
- The version authority is the portable version manifest
  `packages/skills/package.json`; the first `CHANGELOG.md` heading must carry
  the same version. `task version:check` enforces the alignment.

## Adding or Changing the Package

Renaming the distribution, the import package, or the console command is a
full-fidelity migration, not an edit: it touches the PyPI name, every
installation record, the docs, and the install how-to. Do it only through an
OpenSpec change.

## Publishing

Publication is automated and runs only from a tag:

- `.github/workflows/publish.yml` runs from the tagged commit. A tag on
  `main` publishes the Pages root and creates the GitHub Release; a tag on a
  `release/vX.Y` maintenance line creates the GitHub Release without touching
  the Pages root.
- The PyPI upload uses trusted publishing (GitHub OIDC) from `main` tags; no
  PyPI token is stored. The workflow refuses untagged or non-tag runs.
- Every successful `dev` push publishes the PyPI prerelease `skillmate`
  `{version}.dev{run}` through the same trusted-publishing environment; the
  run number is shared with the Pages dev version. Prereleases are immutable:
  a broken one is yanked on the PyPI project page and superseded by the next
  push. Until the first stable release exists, `uvx skillmate` resolves the
  newest prerelease; afterwards select it with `uvx --prerelease skillmate`.
  `--from-checkout` remains the registry-free path for unpushed working-tree
  content.

The release discipline (version mirrors, changelog, confirmation gates,
annotated tags) lives in the `pypi-package-lifecycle` project skill and
`docs/how-to` release flow: never rewrite a published version or tag; a
corrective release is a new patch version.

## Verifying a Release

```shell
uvx skillmate --version
uvx skillmate status
```

After tagging, the publish workflow verifies the deployed Pages artifact and
the GitHub Release postconditions; `task release:check` validates the local
alignment before the tag exists.

## Retiring a Version

PyPI does not allow reuse of a released filename; published versions are
history. Yank a broken release from the PyPI project page when it must not be
resolved by accident, and cut a corrective patch release. Record the reason
in the changelog.
