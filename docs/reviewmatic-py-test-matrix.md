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
| `cli.js` | `reviewmatic.cli` (stage-1 surface; business dispatch lands with each ported module) |
| `local-review.js` | planned: `reviewmatic.local_review` |
| `draft.js` | planned: `reviewmatic.draft` |
| `context-package.js` | planned: `reviewmatic.context_package` |
| `scope.js` | planned: `reviewmatic.scope` |
| `fixes.js` | planned: `reviewmatic.fixes` |
| `schema-issues.js` | planned: `reviewmatic.schema_issues` |
| `worktree.js` | planned: `reviewmatic.worktree` |
| `review-worktree.js` | planned: `reviewmatic.review_worktree` |
| `version.js` | `reviewmatic.__version__` (package metadata) |
| `tui/*` | out of scope for stage 2 (stage 3 keeps the interface experimental) |

## File-by-file matrix

| TypeScript test file | TS tests | Status | Python seam |
| - | - | - | - |
| `cli.test.mjs` | 4 | planned (business dispatch) | `tests/test_cli_contract.py` keeps the stage-1 surface coverage |
| `context-package.test.mjs` | 15 | planned | `tests/test_context_package.py` |
| `context.test.mjs` | 6 | partial | `tests/test_context_report.py` carries the report regressions; collection regressions land with the context port |
| `contract.test.mjs` | 38 | partial | `tests/test_contract_validators.py` (validators, labels, preview, critic/decision bindings), `tests/test_golden_parity.py` (canonical digests, artifact verdicts), `tests/test_cli_contract.py` (capabilities); transport/collection cases land with the local-review port |
| `draft-input.test.mjs` | 13 | planned | `tests/test_draft_input.py` |
| `draft.test.mjs` | 6 | planned | `tests/test_draft.py` |
| `glab-transport.test.mjs` | 1 | planned | `tests/test_glab_transport.py` |
| `local-panel.test.mjs` | 1 | planned | `tests/test_local_panel.py` |
| `local-review.test.mjs` | 26 | planned | `tests/test_local_review.py` (ancestor `tests/test_local_review.py` at `320520a^` is the revival base) |
| `mutation-process.test.mjs` | 6 | planned | `tests/test_mutation_process.py` |
| `panel.test.mjs` | 4 | planned | `tests/test_panel.py` |
| `publication.test.mjs` | 3 | partial | `tests/test_context_report.py::test_publication_make_command_keeps_plain_glab_commands` and `::test_structured_preview_accepts_manual_actions` |
| `repair.test.mjs` | 13 | planned | `tests/test_repair.py` |
| `review-contract-regressions.test.mjs` | 15 | partial | `tests/test_contract_validators.py` carries the canon validator regressions |
| `review-semver.test.mjs` | 11 | covered upstream | `tests/test_review_semver.py` (repository suite) plus the `semver_*` golden fixtures |
| `review-worktree.test.mjs` | 17 | planned | `tests/test_review_worktree.py` |
| `state-artifacts.test.mjs` | 11 | covered upstream | `tests/test_state_artifacts.py` (repository suite) plus the golden marker fixtures |
| `test-selection.test.mjs` | 1 | not applicable | the backend selection is a TypeScript runner concern; the pytest suite has no TUI split |
| `tui-app.test.mjs` | 3 | intentionally reduced | stage 3 (TUI); stage 2 keeps the `plan` command answering the stage-1 not-implemented envelope |
| `tui-pty.test.mjs` | 1 | intentionally reduced | stage 3 (TUI) |
| `tui-support.test.mjs` | 2 | intentionally reduced | stage 3 (TUI) |
| `workflow.test.mjs` | 2 | partial | revived `reviewmatic.workflow` is exercised through `tests/test_context_report.py`; the dispatch regression lands with the CLI wiring |
| `worktree.test.mjs` | 2 | planned | `tests/test_worktree.py` |

The "planned" rows are the remaining stage-2 delta; the seam files above are
the agreed landing spots so no TypeScript test is lost silently. The matrix is
updated in the same change that lands each row.

## Fake glab

The TypeScript suite drives `helpers/review-fixture.mjs`, which writes a
Node-script fake `glab` onto `PATH` and records every request. The Python port
rewrites this helper as a Python fake with the same recorded-request contract;
the ported request-log tests carry the parity evidence. This keeps the package
tests standard-library-only instead of depending on a Node runtime.
