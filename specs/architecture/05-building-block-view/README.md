# Building Block View

- `skills/` contains 29 authored capability definitions and unique resources.
- `shared/` and `shared/manifest.json` contain canonical reusable material and
  exact build destinations.
- `packages/skills/`, `build_skills.py`, and `build_distribution.py` define the
  private build and public Pages distribution boundary.
- `.github/workflows/pages.yml` validates release provenance and deploys Pages.
- `packages/opencode/src/` contains catalog, registry, plugins, routing, tools,
  installer, profiles, lifecycle, and state adapters.
- `packages/opencode/test/` contains package lifecycle and security contracts.
- `tests/` contains repository, distribution, workflow, and eval contracts.
- `evals/` contains machine-readable scenarios, fixtures, schemas, and negative
  corpus entries.
- `specs/` is the canonical normative model and traceability index.
