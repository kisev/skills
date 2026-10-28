---
name: pypi-package-lifecycle
description: Use when adding, renaming, versioning, publishing, or retiring the skillmate PyPI distribution or touching its release automation.
---

# PyPI Package Lifecycle

`skillmate` is the repository's only publication channel: the PyPI
distribution `skillmate` under the `kisev` account. Full description:
`docs/how-to/pypi-package-lifecycle.md` (Russian mirror in `docs/ru/how-to/`).

## Rules

- Publication is tag-driven and automated: `.github/workflows/publish.yml`
  runs from the tagged commit; the PyPI upload uses trusted publishing
  (GitHub OIDC) from `main` tags. No PyPI token is stored anywhere.
- The version authority is the portable version manifest
  `packages/skills/package.json`; the first `CHANGELOG.md` heading carries the
  same version. `task version:check` enforces the alignment.
- Never rewrite a published version or tag; a corrective release is a new
  patch version. Registry propagation alone is never a reason to bump.
- Every successful `dev` push publishes the PyPI prerelease
  `{version}.dev{run}` through the same trusted publishing; prereleases are
  immutable, and a broken one is yanked and superseded by the next push.
  `--from-checkout` remains the registry-free path for unpushed content.
- Renaming the distribution, import package, or console command is a
  full-fidelity migration through an OpenSpec change, never a direct edit.

## Boundaries

- Require explicit confirmation before merging into `main` and again before
  creating and pushing the annotated tag, with no publication run active or
  pending.
- Do not publish manually with `twine` or store API tokens; the workflow is
  the only publication path.
- Until the first stable release, document the tool as installable through
  `uvx skillmate` and `pip install skillmate` without claiming a published
  version.
