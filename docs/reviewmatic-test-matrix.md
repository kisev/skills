# reviewmatic Test Baseline and Port Matrix

[Русская версия](ru/reviewmatic-test-matrix.md)

The saved TypeScript baseline was measured before removal at source revision
`3e409c217e94d643f77eb543caab9a2ed4b7288d`. With the package built from that
checkout, the baseline was
`node --test --test-reporter=tap` over `apps/reviewmatic/test/*.test.mjs`:
**201 tests, 201 pass, 0 failed, 0 skipped** (26 files). The backend selection
was **195 tests, 195 pass**; the three TUI files (`tui-app`, `tui-pty`,
`tui-support`) contributed the remaining 6. The Python baseline is verified by
`task reviewmatic:check` and `task test:python`; no TypeScript test runner or
generator remains in the repository.

## Dist module to Python seam map

| TypeScript module (`dist/<name>.js`) | Python seam |
| - | - |
| `contract.js` | `reviewmatic.portable.portable_gitlab.contract` (materialized canon) |
| `state-artifacts.js` | `reviewmatic.portable.state_artifacts` (materialized canon) |
| `mutation-process.js` | `reviewmatic.portable.mutation_process` (materialized canon) |
| `review-semver.js` | `reviewmatic.portable.portable_gitlab.review_semver` (materialized canon) |
| `label-assessment.js` | `reviewmatic.portable.portable_gitlab.label_assessment` (materialized canon) |
| `context.js` | `reviewmatic.context` (revived from the pre-port reference) |
| `workflow.js` | `reviewmatic.workflow` (revived from the pre-port reference) |
| `publication.js` | `reviewmatic.publication` (translated from the TypeScript source) |
| `cli.js` | `reviewmatic.cli` (review and local-WIP commands; the TUI-only `plan` command is removed) |
| `local-review.js` | `reviewmatic.local_review` (translated from the TypeScript source) |
| `draft.js` | `reviewmatic.draft` (translated from the TypeScript source; the complete state machine) |
| `context-package.js` | `reviewmatic.context_package` (translated from the TypeScript source) |
| `scope.js` | `reviewmatic.scope` (translated from the TypeScript source) |
| `fixes.js` | `reviewmatic.fixes` (translated from the TypeScript source) |
| `schema-issues.js` | `reviewmatic.schema_issues` (translated; the canon registers `schema_valid` as its oracle at package import) |
| `worktree.js` | `reviewmatic.worktree` (translated from the TypeScript source) |
| `review-worktree.js` | `reviewmatic.review_worktree` (translated from the TypeScript source) |
| `version.js` | `reviewmatic.__version__` (package metadata) |
| `tui/*` | removed with the TypeScript application; no replacement interface |

## File-by-file matrix

| TypeScript test file | TS tests | Status | Python seam |
| - | - | - | - |
| `cli.test.mjs` | 4 | ported | `tests/test_cli_contract.py` (version/help/capabilities/publication/marker-run surface, now with the stage-2 business dispatch assertions) |
| `context-package.test.mjs` | 15 | ported | `tests/test_context_package.py` (digests, versioning, retirement, answer/verification bindings, MR validation) and `tests/test_context_package_records.py` (all fifteen end-to-end record scenarios through the fake glab; the located schema diagnostics come from the canon schema-issue locator registered at package import) |
| `context.test.mjs` | 6 | ported | `tests/test_context_report.py` (report regressions), `tests/test_review_happy_path.py` (fake-glab state machine happy path), `tests/test_context_scenarios.py` (runner action, progress transitions, line publications, verdict gating, atomic state publication, and the unchanged second-run tail) |
| `contract.test.mjs` | 38 | ported | `tests/test_contract_scenarios.py` (all thirty-eight scenarios, with inline Python fake glabs through `tests/helpers/contract_support.py`), `tests/test_contract_validators.py`, `tests/test_golden_parity.py`, `tests/test_cli_contract.py`; the `glab_text`, trace, and semver parsers return tuples in Python |
| `draft-input.test.mjs` | 13 | ported | `tests/test_draft_input_scenarios.py` (all thirteen scenarios; the CLI-driven ones run `python -m reviewmatic`; TUI-only plan helpers are reduced to the plan artifact and its preview actions), plus `tests/test_draft_lifecycle.py` |
| `draft.test.mjs` | 6 | ported | `tests/test_draft_scenarios.py` (all six scenarios; the `amendBody` and `itemText` TUI assertions are reduced to plan-level equivalents) plus `tests/test_draft_lifecycle.py` |
| `glab-transport.test.mjs` | 1 | ported | `tests/test_glab_transport.py` (the pinned real glab against a loopback server; no skip) |
| `local-panel.test.mjs` | 1 | ported | `tests/test_local_panel.py` |
| `local-review.test.mjs` | 26 | ported | `tests/test_local_review_cycle.py` (fix cycle, verdict), `tests/test_local_review_preparation.py` (eighteen preparation, boundary, and CLI scenarios), `tests/test_local_review_scenarios.py` (six package-binding scenarios; `finalize-local` rejects a stale answer for local snapshots after the canon `evidence_kind` fix) |
| `mutation-process.test.mjs` | 6 | ported | `tests/test_mutation_process.py` |
| `panel.test.mjs` | 4 | ported | `tests/test_panel.py` (the TUI `loadPlan` helper is replaced by reading the plan artifact through the progress pointer) |
| `publication.test.mjs` | 3 | ported / UI-only removed | `tests/test_context_report.py` and `tests/test_publication_scenarios.py` cover runbook commands and fake-glab head guards; `AbortSignal` cancellation belonged only to the removed TUI |
| `repair.test.mjs` | 13 | ported | `tests/test_fixes_and_diagnostics.py` (schema diagnostics, suggestion synthesis) and `tests/test_repair.py` (end-to-end repair, refresh, and CI-drift scenarios; the TUI `planItems` assertion is reduced to the publication preview actions it derives from) |
| `review-contract-regressions.test.mjs` | 15 | ported | `tests/test_review_contract_regressions.py` (all eleven definitions); routing-reply assertions use the draft field and generated runbook blocks, with no TUI adapter |
| `review-semver.test.mjs` | 11 | covered upstream | `tests/test_review_semver.py` (repository suite) plus the `semver_*` golden fixtures |
| `review-worktree.test.mjs` | 17 | ported | `tests/test_review_worktree.py` (unit rules) and `tests/test_review_worktree_scenarios.py` (all seventeen end-to-end scenarios with real subprocess concurrency) |
| `state-artifacts.test.mjs` | 11 | covered upstream | `tests/test_state_artifacts.py` (repository suite) plus the golden marker fixtures |
| `test-selection.test.mjs` | 1 | not applicable | the backend selection is a TypeScript runner concern; the pytest suite has no TUI split |
| `tui-app.test.mjs` | 3 | removed with interface | Ink navigation and send behavior do not exist in the Python runtime |
| `tui-pty.test.mjs` | 1 | removed with interface | no terminal UI or PTY command |
| `tui-support.test.mjs` | 2 | removed with interface | terminal-only presentation helpers are not runtime behavior |
| `workflow.test.mjs` | 2 | ported | `tests/test_workflow_dispatch.py` |
| `worktree.test.mjs` | 2 | ported | `tests/test_worktree.py` (both scenarios plus guarded removal, which the TypeScript suite does not cover) |

Every backend behavior test has a Python seam. The TypeScript test-selection
runner check is not an application behavior and was removed with that runner.
The six TUI tests are removed only with the interface; their old behavior is
not represented as a test skip. Golden fixtures retain TypeScript-generated digests, verdicts, and the
`draft_gaps`, `superseded_results`, and `analysis_fingerprint` transition
outputs. Python recomputes and asserts every expectation; it never regenerates
the expected values from itself.

## Fake glab

The TypeScript suite drives `helpers/review-fixture.mjs`, which writes a
Node-script fake `glab` onto `PATH` and records every request. The Python port
rewrites this helper as a Python fake with the same recorded-request contract;
the ported request-log tests carry the parity evidence. This keeps the package
tests standard-library-only instead of depending on a Node runtime.
