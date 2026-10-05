# reviewmatic Python Test Matrix

[Русская версия](ru/reviewmatic-py-test-matrix.md)

The authoritative TypeScript count on this revision is
`node --test --test-reporter=tap` over `apps/reviewmatic/test/*.test.mjs`:
**201 tests, 201 pass, 0 failed, 0 skipped** (26 files; the three TUI files
`tui-app`, `tui-pty`, `tui-support` hold 6 of them). The backend selection that
`apps/reviewmatic` runs itself (`scripts/test.mjs`, all files except the TUI
set) is **195 tests, 195 pass**. Both numbers were produced on the revision
that introduced this file with the built `dist/` output.

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
| `cli.js` | `reviewmatic.cli` (every business subcommand wired with the TypeScript exit codes; `plan` keeps the exit-5 envelope until stage 3) |
| `local-review.js` | `reviewmatic.local_review` (translated from the TypeScript source) |
| `draft.js` | `reviewmatic.draft` (translated from the TypeScript source; the complete state machine) |
| `context-package.js` | `reviewmatic.context_package` (translated from the TypeScript source) |
| `scope.js` | `reviewmatic.scope` (translated from the TypeScript source) |
| `fixes.js` | `reviewmatic.fixes` (translated from the TypeScript source) |
| `schema-issues.js` | `reviewmatic.schema_issues` (translated; the canon registers `schema_valid` as its oracle at package import) |
| `worktree.js` | `reviewmatic.worktree` (translated from the TypeScript source) |
| `review-worktree.js` | `reviewmatic.review_worktree` (translated from the TypeScript source) |
| `version.js` | `reviewmatic.__version__` (package metadata) |
| `tui/*` | out of scope for stage 2 (stage 3 keeps the interface experimental) |

## File-by-file matrix

| TypeScript test file | TS tests | Status | Python seam |
| - | - | - | - |
| `cli.test.mjs` | 4 | ported | `tests/test_cli_contract.py` (version/help/capabilities/publication/marker-run surface, now with the stage-2 business dispatch assertions) |
| `context-package.test.mjs` | 15 | ported | `tests/test_context_package.py` (digests, versioning, retirement, answer/verification bindings, MR validation) and `tests/test_context_package_records.py` (all fifteen end-to-end record scenarios through the fake glab; the located schema diagnostics come from the canon schema-issue locator registered at package import) |
| `context.test.mjs` | 6 | partial | `tests/test_context_report.py` (report regressions), `tests/test_review_happy_path.py` (fake-glab state machine happy path with the incremental second run) |
| `contract.test.mjs` | 38 | partial | `tests/test_contract_validators.py` (validators, labels, preview, critic/decision bindings), `tests/test_golden_parity.py` (canonical digests, artifact verdicts), `tests/test_cli_contract.py` (capabilities); transport/collection cases land with the local-review port |
| `draft-input.test.mjs` | 13 | partial | `tests/test_draft_lifecycle.py` (record-input addressed diagnostics, record-critic missing-binding rejection) plus `tests/test_contract_validators.py`; the full record-package/record-critic scenarios await the input fixtures |
| `draft.test.mjs` | 6 | partial | `tests/test_draft_lifecycle.py` (full remote lifecycle through the fake glab: invalid check, complete-draft contract, zero-request finish, plan\_ready; plan-inspection/sendItem assertions stay with the TUI-support row) |
| `glab-transport.test.mjs` | 1 | ported | `tests/test_glab_transport.py` (the pinned real glab against a loopback server; no skip) |
| `local-panel.test.mjs` | 1 | ported | `tests/test_local_panel.py` |
| `local-review.test.mjs` | 26 | partial | `tests/test_local_review_cycle.py` (the full fix cycle with the incremental delta, unchanged reuse, ready transition, verdict derivation); the panel and arbitration scenarios await the local-panel fixtures |
| `mutation-process.test.mjs` | 6 | ported | `tests/test_mutation_process.py` |
| `panel.test.mjs` | 4 | ported | `tests/test_panel.py` (the TUI `loadPlan` helper is replaced by reading the plan artifact through the progress pointer) |
| `publication.test.mjs` | 3 | partial | `tests/test_context_report.py::test_publication_make_command_keeps_plain_glab_commands` and `::test_structured_preview_accepts_manual_actions` |
| `repair.test.mjs` | 13 | ported | `tests/test_fixes_and_diagnostics.py` (schema diagnostics, suggestion synthesis) and `tests/test_repair.py` (end-to-end repair, refresh, and CI-drift scenarios; the TUI `planItems` assertion is reduced to the publication preview actions it derives from) |
| `review-contract-regressions.test.mjs` | 15 | partial | `tests/test_contract_validators.py` carries the canon validator regressions |
| `review-semver.test.mjs` | 11 | covered upstream | `tests/test_review_semver.py` (repository suite) plus the `semver_*` golden fixtures |
| `review-worktree.test.mjs` | 17 | partial | `tests/test_review_worktree.py` (slugs, remote matching, checkout rejection, registry, locking); the end-to-end preparation scenarios land with the draft port and the fake-glab helper |
| `state-artifacts.test.mjs` | 11 | covered upstream | `tests/test_state_artifacts.py` (repository suite) plus the golden marker fixtures |
| `test-selection.test.mjs` | 1 | not applicable | the backend selection is a TypeScript runner concern; the pytest suite has no TUI split |
| `tui-app.test.mjs` | 3 | intentionally reduced | stage 3 (TUI); stage 2 keeps the `plan` command answering the stage-1 not-implemented envelope |
| `tui-pty.test.mjs` | 1 | intentionally reduced | stage 3 (TUI) |
| `tui-support.test.mjs` | 2 | intentionally reduced | stage 3 (TUI) |
| `workflow.test.mjs` | 2 | ported | `tests/test_workflow_dispatch.py` |
| `worktree.test.mjs` | 2 | ported | `tests/test_worktree.py` (both scenarios plus guarded removal, which the TypeScript suite does not cover) |

The "planned" rows are the remaining stage-2 delta; the seam files above are
the agreed landing spots so no TypeScript test is lost silently. The matrix is
updated in the same change that lands each row.

## Fake glab

The TypeScript suite drives `helpers/review-fixture.mjs`, which writes a
Node-script fake `glab` onto `PATH` and records every request. The Python port
rewrites this helper as a Python fake with the same recorded-request contract;
the ported request-log tests carry the parity evidence. This keeps the package
tests standard-library-only instead of depending on a Node runtime.
