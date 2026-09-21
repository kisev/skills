# Building Block View

- `skills/` contains 27 authored capability definitions and unique resources.
- `shared/` and `shared/manifest.json` contain canonical reusable material and
  exact build destinations.
- `packages/skills/`, `build_skills.py`, and `build_distribution.py` define the
  private build and public Pages distribution boundary.
- `.github/workflows/publish.yml` gates, builds, publishes, and verifies both
  release channels before creating the GitHub Release.
- `packages/opencode/src/` contains catalog, registry, plugins, routing, CLI,
  installer, profiles, lifecycle, and state adapters.
- `packages/opencode/test/` contains package lifecycle and security contracts.
- `tests/` contains repository, distribution, workflow, and eval contracts.
- `evals/` contains machine-readable scenarios, fixtures, schemas, and negative
  corpus entries.
- `specs/` is the canonical Markdown normative model.
- `skills/spec-manage/scripts/spec_validate.py` is the self-contained read-only
  formal validator shipped as an authored asset of that skill; it is not shared
  through `shared/manifest.json` without another confirmed consumer.
