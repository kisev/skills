# Release MR preparation

Read `references/interaction-contract.md`, `references/gitlab-workflow.md`, `references/portable-gitlab-contracts-v2.md`, `references/label-semantics.md`, `references/language-policy.md`, and `references/release-examples.md`. Accept exactly one release MR URL; do not infer it from a branch and do not create a batch.

Collect the MR evidence first. Treat `diff_refs.head_sha` as the release head and verify that the local checkout resolves it exactly. The release MR source branch is the component MR target branch. Do not substitute local `HEAD` without proving equality.

Select the nearest matching SemVer `v*` tag on the first-parent ancestry of the release head, or use an explicitly confirmed previous boundary. Verify ancestry. When no tag exists, include the root commit. Do not select a tag by creation date and do not fetch refs implicitly.

Create the inventory with `scripts/prepare_release.py inventory --evidence <evidence-path> --repo-root <checkout>`. Add `--previous-ref <tag-or-sha>` only for an explicit boundary. The helper resolves every release commit, paginates its associated MRs, deduplicates by IID, and records non-merge commits without an associated MR as direct commits. Any unresolved range, association error, truncation, or incomplete MR evidence makes the inventory incomplete.

Verify release items against available MR text, commit subject/body, diff, discussions, and linked context. Do not widen collection to fetch project templates, linked issues, users, or historical approvals. Preserve verified MR and direct-commit authors; explicitly list unavailable issue, reviewer, and template context.

Choose MAJOR, MINOR, or PATCH from observable compatibility, configuration, schema, API, default, migration, and deprecation changes. Do not claim backward compatibility without evidence. Present the rationale and obtain the user's version decision before scaffolding final artifacts; normalize the version without a duplicate `v` prefix.

Prepare the title, description, and announcement in the language of the latest user request; use English when that language is ambiguous. Every release item states the change, impact, required action, and source `!IID` or linked 7-character commit SHA. Keep the compatibility and migration section even when no action is required. The announcement has 3-5 concise outcome-focused items. Prepare an English 16:9 illustration prompt without text, letters, numbers, code, logos, interfaces, or invented claims. Set semantic `change_type=release` and the confirmed `compatibility` impact; use no concrete label names and leave unsupported roles `null`.

Put exactly `title`, `description`, `version`, `announcement`, `illustration_prompt`, and `label_intent` in the scaffold content JSON. `label_intent` uses only roles and values from `label-semantics.md`. Create the plan with `scripts/prepare_release.py scaffold --bundle <evidence-path> --inventory <inventory-path> --content <content-path>`. It writes an immutable JSON envelope, a Markdown plan, separate immutable release description, announcement and illustration-prompt companions, and a read-only semantic label delta. It does not provide mutation commands.

Report `success`, `running`, `failed`, `canceled`, or `missing` only for a pipeline whose SHA equals the release head. Mention success only when confirmed; expose incomplete or unsupported states.

Immediately before manual publication, run `scripts/prepare_release.py finalize --plan <publication-plan-path>`. Changed exact base/start/head SHA, MR object, label catalog or current labels, discussions, diff, commits, pipelines, release boundary, commit associations, inventory completeness, unresolved semantic intent, or any modified artifact blocks readiness. Do not create, update, approve, merge, push, mutate labels, publish a GitLab Release, choose a Mattermost channel, or send the announcement.
