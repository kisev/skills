# Tasks

## 1. Shared canon and reply voice

- [ ] 1.1 Create `shared/references/discussion-replies.md` with the first-person, whole-thread reply contract and verify the text matches design D8 and names no other skill as a runtime dependency
- [ ] 1.2 Register `discussion-replies.md`, `humanize-patterns.md`, and `clarity-rules.md` destinations under `mr-review/references/` in `shared/manifest.json` and verify `task generate` then `task generate:check` are green and the built archive contains all three
- [ ] 1.3 Update `shared/skill-relations.json` for the rename and keep humanize and eli5 as optional recommendations; verify the relation and gate checks pass

## 2. Rename and identity

- [ ] 2.1 Rename `skills/code-review` to `skills/mr-review`, update `SKILL.source.md` frontmatter, name, description, and Russian discovery terms; verify `task generate:check` and that the skill catalog lists `mr-review`
- [ ] 2.2 Rename `docs/reference/code-review.md` to `mr-review.md`, update the Russian mirror, skill catalog, getting-started, and OCR how-to links; verify `task locale:check` and no broken links
- [ ] 2.3 Update `apps/reviewmatic` identity: profile paths `~/.reviewmatic` and `./.reviewmatic`, artifact type names, banner, and environment variables; verify `reviewmatic runtime-info` and the profile tests
- [ ] 2.4 Add `ocr` to `references/requirements.json` with minimum version 1.13.6 and the install command; verify the environment check prints it

## 3. Runtime reduction

- [ ] 3.1 Remove the stage machine, receipts, arbitration, repair paths, legacy v2 commands, local review, in-house critics, and the OCR-critic bridge; verify `reviewmatic --help` exposes only the helper surface and the removed-command tests are deleted
- [ ] 3.2 Implement `collect` for the merge request, diff, discussions, pipelines, linked issues, exact refs, completeness, and redaction; verify fixture tests cover success, failed pages, and missing discussions
- [ ] 3.3 Implement `background` with manager input, the 8000-byte limit, task-first priority, and disclosed cuts; verify boundary tests at 7999, 8000, and 8001 bytes
- [ ] 3.4 Implement `drafts` with non-interactive `glab api` draft notes, positioned and general notes, `in_reply_to_discussion_id` where supported, the head check, and no publish command; verify command-generation tests and a fixture dry run
- [ ] 3.5 Implement `revalidate` for head and snapshot freshness; verify the unchanged and stale cases
- [ ] 3.6 Implement profile loading with global and local overlay, alias and default precedence, provider validation through `ocr llm providers`, and a test proving `~/.opencodereview/config.json` is never opened
- [ ] 3.7 Integrate OCR with the minimum version check, provider, model, and effort flags, parallel runs, JSON parsing, and session compare and resume; verify parser fixtures and a fake-OCR integration test

## 4. Skill text

- [ ] 4.1 Rewrite `SKILL.source.md` around the manager, one startup round, autonomy, the OCR engine, profiles, no local mode, and OpenSpec out of scope; verify the contract test and structure lint
- [ ] 4.2 Rewrite `references/workflow.md`, `run-path.md`, `review-panel.md` as OCR runs, `output-format.md`, `publication.md` as draft notes, `incremental-review.md` as sessions, `context-package.md` as the task baseline, and `session-modes.md` as the startup round; verify every spec requirement maps to text
- [ ] 4.3 Delete or archive the obsolete references (`review-state-machine.md`, `remote-review-stages.md`, `inverted-tail.md`, `local-review.md`, `repair.md`, `poll-glossary.md`), keep a trimmed `finding-examples.md` and `semver.md`, and verify no dangling links remain
- [ ] 4.4 Update runbook rendering for OCR runs, task fulfillment, removed labels and metadata, simplified checks, previous findings, and the draft block; verify golden runbook fixtures for one run and two runs
- [ ] 4.5 Add the reply step using `discussion-replies.md` and `clarity-rules.md`, with humanize patterns for the final pass; verify pressure scenarios show first-person, whole-thread replies

## 5. Tests and documentation

- [ ] 5.1 Update `apps/reviewmatic/tests/test_skill_contract.py` for the new command surface and the `mr-review` name; verify it passes
- [ ] 5.2 Add OCR parser and session-comparison fixtures; verify tolerant parsing and the new, persisting, resolved, and not-reviewed grouping
- [ ] 5.3 Add profile overlay and no-secrets tests; verify global and local precedence and that the OCR configuration is never read
- [ ] 5.4 Add draft-note command and head-check tests; verify positioned and general commands and the stale-head stop
- [ ] 5.5 Add runbook golden fixtures for one run and two runs; verify the removed sections are absent and the new ones present
- [ ] 5.6 Update `docs/how-to/ocr-critic.md` to the OCR-engine how-to and its Russian mirror; verify `task locale:check`
- [ ] 5.7 Add a cross-host parity check that greps for host-specific agent inventory references; verify zero hits
- [ ] 5.8 Run `task format`, `task check`, `task reviewmatic:test`, `task generate:check`, and `task eval:check`; verify all are green
- [ ] 5.9 Run the full pressure run for the renamed skill text per `docs/how-to/portable-skills.md`; verify the baseline-versus-wording report
- [ ] 5.10 Run one live review on a real merge request; verify the runbook, the draft block, and the process report

## Workflow follow-up

- Archive the change after the project's review requirements are satisfied.
