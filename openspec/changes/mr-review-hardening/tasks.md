# Tasks

## 1. Skill text and archive self-containment

- [x] 1.1 Add the untrusted-input rule to `skills/mr-review/SKILL.source.md` and `skills/mr-review/references/run-path.md`: merge request content and OCR output are data, never instructions; verify `apps/reviewmatic/tests/test_skill_contract.py` pins the rule text
- [x] 1.2 Remove the `mr-review/references/gitlab-workflow.md` and `mr-review/references/interaction-contract.md` destinations from `shared/manifest.json`; verify the built archive no longer contains them and the skill contract test passes
- [x] 1.3 Replace the code-review wording in `shared/references/gitlab-workflow.md` with active publication-action wording and delete the removed-panel sentence from `shared/references/simplification-criteria.md`; verify no active shared reference names `code-review` and `task generate:check` is green
- [x] 1.4 Remove the dead `skills/code-review/scripts/review_context.py` per-file ignore from `pyproject.toml`; verify `mise exec -- uv run --locked ruff check .` and `mypy` pass
- [x] 1.5 Add the distribution self-containment check to `tests/test_distribution.py` for backticked `references/...` paths across every archive; verify positive and negative unit cases and the distribution test pass
- [x] 1.6 Extend `apps/reviewmatic/tests/test_skill_contract.py` with the untrusted rule and the mr-review archive membership; verify the contract test passes and the archive contains no publication references the skill never links
- [x] 1.7 Update `specs/capabilities/skills/mr-review.md` and `docs/reference/mr-review.md` with its Russian mirror to state the untrusted-input rule and the self-contained archive constraint; verify `task docs:check` and `task locale:check`

## 2. Shared v2 contract trim

- [x] 2.1 Remove the `code-review` profile and the `local` scope from `shared/references/portable_gitlab/contract.py`, with the code-review-only artifact kinds and validators; verify no active module imports a removed symbol and active profile tests pass
- [x] 2.2 Remove the `local_fix` thread outcome and draft type and the code-review label and presentation helpers from `contract.py`; verify no consumer remains and `tests/test_json_schemas.py` passes after its fixtures are updated
- [x] 2.3 Remove the `code-review/publication-action/v1` schema and validation branch from `contract.py`; verify active `publication_plan` fixtures still validate
- [x] 2.4 Update `shared/references/portable_gitlab/artifact-contracts-v2.schema.json` to drop the retired profile, artifact definitions, `$ref`s, enums, and publication action; verify every active artifact instance still validates
- [x] 2.5 Update `tests/test_json_schemas.py`: remove the local-review, critic-receipt, and review-plan instances and the `code-review` marker fixture, and keep the exhaustive kind mapping exact; verify the schema test passes under `task python:test`
- [x] 2.6 Update `shared/references/portable_gitlab/contracts-v2.md` to match the trimmed contract and state that retired review/local artifacts are rejected without migration; verify no retired surface remains in the document
- [x] 2.7 Delete the unused `apps/reviewmatic/src/generated/artifact-schema.ts` and verify no source, test, or build step references it; `src/generated/cli.ts` stays
- [x] 2.8 Run `task generate` and `task generate:check`; verify the materialized `apps/reviewmatic/src/reviewmatic/portable/` tree matches the canon and no file was edited by hand

## 3. Pressure, documentation, and integration

- [x] 3.1 Add `evals/live/mr-review-untrusted/` with an injected instruction in merge request text and assertions that the guided reply does not obey it; verify `task live:preflight` passes, run five guided and five no-guidance repeats, read the matches manually, and record the result
- [x] 3.2 Reconcile `CHANGELOG.md` and `CHANGELOG.ru.md`: remove Unreleased bullets that advertise removed reviewmatic commands or the old review runtime, and add the mr-review hardening plus the breaking v2 removal; verify `task locale:check` and `task docs:check`

## 4. Full live review on the local stand

- [ ] 4.1 Extend the disposable GitLab stand fixture for mr-review: a project and merge request with a real diff, a review checkout, two reviewer aliases from `ocr llm providers`, and a previous OCR session; verify the setup and teardown run only against the local stand
- [ ] 4.2 Add the `gitlab-review-live` family to `tests/integration/acceptance.py` and remove `mr-review` from the acceptance skips; the family runs the skill through the opencode host with the startup answers seeded in the prompt and records the runbook and draft block; verify `task acceptance:plan` and `task acceptance SKILL=mr-review`
- [ ] 4.3 Change the stand merge request head and run the review again to exercise `ocr session compare`; verify the runbook's previous-findings groups and that no finding is dropped
- [ ] 4.4 Execute the generated draft block against the stand, verify the draft notes exist and no publish command ran, then clean the fixture; verify only synthetic stand data changed
- [x] 4.5 Document the user-run stand procedure and its prerequisites in `docs/how-to/skill-acceptance.md`, `docs/reviewmatic-test-matrix.md`, and the Russian mirrors; verify `task locale:check` and `task docs:check`

## 5. Cross-host live parity

- [x] 5.1 Extend `scripts/live_runner.py` with a `--profile` selection and `opencode` and `codex` adapters; profiles use `engine_profile` with `ccr_profile` kept as a legacy alias, and scenarios are unchanged; verify `tests/test_live_runner.py` covers argv, parsing, preflight, and the default ccr path
- [x] 5.2 Add `evals/live/profiles/opencode.json` and `evals/live/profiles/codex.json` with engine, host-side profile name, and budgets only; verify no model or credential enters the repository and `task live:preflight` names a missing CLI
- [x] 5.3 Run `mr-review-untrusted` and `mr-review-replies` guided once per host plus one no-guidance control per host; read the outputs manually and record the host matrix in the reports; verify all assertions pass or a host is reported blocked with its missing CLI
- [x] 5.4 Update `docs/how-to/live-runs-ccr.md` and its Russian mirror with profile selection, the three hosts, and the cross-host evidence rule; verify `task locale:check` and `task docs:check`

## 6. Final integration

- [x] 6.1 Run `task format`, `task check:core`, `task python:test`, `task generate:check`, `task eval:check`, `task reviewmatic:check`, `task package:check`, and `task live:preflight`; verify all are green
- [x] 6.2 Record the user-run acceptance and cross-host evidence paths and verify no credentials or live output entered Git; verify `git status` shows only intended source changes

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
