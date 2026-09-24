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

## Dependency and ownership boundaries

The build depends on authored skills and shared inputs; installed skills depend
only on their materialized local resources. The OpenCode adapter depends on the
public skill names, never on a portable installation tree. These boundaries provide
[REQ-I-001](../../requirements/interfaces/README.md#req-i-001---skill-interface) and
[REQ-I-002](../../requirements/interfaces/README.md#req-i-002---command-interface).

For code-review, `review_workflow.py` owns stage orchestration and injects its
dispatcher into the shared CLI. `review_context.py` owns exact review context and
plan assembly. `review_publication.py` owns separate guarded writes. The shared
GitLab contract supplies evidence, artifact validation, and transport primitives;
it does not import review implementation modules. `mutation_process.py` supplies
bounded process execution to both review publication and task triage. These
mechanisms provide [the code-review contract](../../capabilities/skills/code-review.md)
and [REQ-Q-004](../../requirements/quality/README.md#req-q-004---evidence-completeness).
