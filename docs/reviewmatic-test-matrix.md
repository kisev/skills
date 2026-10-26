# reviewmatic Test Baseline and Port Matrix

[Русская версия](ru/reviewmatic-test-matrix.md)

The saved TypeScript baseline was measured before removal at source revision
`3e409c217e94d643f77eb543caab9a2ed4b7288d`. With the package built from that
checkout, the baseline was
`node --test --test-reporter=tap` over `apps/reviewmatic/test/*.test.mjs`:
**201 tests, 201 pass, 0 failed, 0 skipped** (26 files). The backend selection
was **195 tests, 195 pass**; the three TUI files (`tui-app`, `tui-pty`,
`tui-support`) contributed the remaining 6. The Python baseline is verified by
`task reviewmatic:check` and `task python:test`; no TypeScript test runner or
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

## Skill acceptance layers

The code-review skill has two acceptance layers on top of its ordinary test
suite (solution 64: committing a broken review cycle must be impossible
deterministically, or immediately visible agentically).

The deterministic layer lives inside the full-cycle tests. The run-cycle test
seeds `closes_issues` and asserts the completed run by artifacts and the
fixture request log: the poll stop hands the agent the verbatim poll text plus
the agent-catalog grounding rules; related issues are collected with their
`author_text` origin; authored Conventional Comments reply labels survive into
the publication plan; and the whole cycle talks to the one fake glab from
`tests/helpers/review_fixture.py`. They run inside `task check` through the
ordinary pytest suite.

The agent layer is `task test:integration:skills:acceptance`
(`tests/integration/gitlab/scripts/skill_acceptance.py`). It builds the
fake-glab fixture, pre-seeds the host agent catalog, pins the reviewmatic
runtime to the current checkout, and asks one real
`opencode run --standalone` session to drive the complete review cycle from
the temporary checkout. Verification is machine-only, over artifacts and the
host's stdout JSONL events: the poll presented verbatim, the composition
question asked through the host's native interactive question tool with the
minimum option set (decision 71; in the non-interactive run the tool use is
cancelled and the pre-given answer stands), the critic receipt
imported, the prose authored, the reading discipline respected (zero
out-of-stage `references/` reads), no publication mutation against the fake
glab, and an independent `reviewmatic report-review` revalidation. It never
parses the host session database.

Honest boundaries of the agent layer: the GitLab host is the fake-glab
fixture rather than a real server, publication stays unexecuted, and
provider/model behavior is not deterministic — a green verdict means one real
model completed the cycle and passed every machine check, with a retry only
for transport-level failures. The critic panel keeps its independence
contract: the acceptance requires the critic to run as an independent
subagent session (opencode's subagent tool provides one) and fails a receipt
signed with the primary session's identity.
The task runs with defaults (the `zai-coding-plan/glm-5.3-flash` model, a
90-minute timeout, and generous token/cost budgets) and stays fully
configurable through the `EVAL_MODEL`, `EVAL_TIMEOUT`, `EVAL_MAX_TOKENS`, and
`EVAL_MAX_COST` environment variables; provider credentials are always
explicit. It is
deliberately outside `task check`, `check:core`, the Lefthook pre-push gate,
the CI matrix, and `gate-registry.json` (same class as `live:run`).

Run the agent layer on every wave that touches the code-review skill texts,
and before a release. Run the deterministic layer whenever anything in the
repository changes; it is an ordinary test.

## The acceptance umbrella

`task acceptance` (`tests/integration/acceptance.py`) is the single launcher
over every live skill family: it drives the agent layer above, the GitLab and
Mattermost live runs, and one minimal behavioral probe per uncovered skill
(`tests/integration/acceptance_probes.py`). Each probe installs only its
skill into an isolated host sandbox, seeds small fixture files, and
machine-checks the produced artifact; skills a synthetic fixture cannot
exercise are skipped with their reason in the report. Every run writes
`result.json` and `summary.md` under `.build/acceptance/<timestamp>/` and
prints line-by-line progress (skill, family, stage, model, elapsed). The
default model is the cheap flash class; any `EVAL_*` variable overrides it,
and a non-cheap model requires explicit `--yes` or `ACCEPT_EXPENSIVE=1`.
The full code-review cycle wall clock is an acceptance criterion of its own:
30 minutes on the fixture above, per stage timed, an overrun is a red
verdict. How to run it, where reports land, and how to hand a report to the
master session live in [the how-to](how-to/skill-acceptance.md). The
umbrella stays outside `task check`, `check:core`, Lefthook, CI, and the
gate registry.
