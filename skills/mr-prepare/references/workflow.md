# Ordinary MR preparation

Read `references/interaction-contract.md`, `references/gitlab-workflow.md`, `references/portable-gitlab-contracts-v2.md`, and `references/language-policy.md`. Accept exactly one MR URL; do not infer an MR from a branch and do not create a batch. The runner collects metadata, changed files, commits, discussions, pipelines for the exact head SHA, and the complete paginated label list.

Verify the title and description against the collected diff, commits, discussions, and linked context that is actually available. Use project templates only when they are already available in the local checkout or collected evidence; do not widen collection to fetch templates, linked issues, `AGENTS.md`, or CONTRIBUTING. Explicitly list unavailable context.

Write a title of 5-10 words that states the resulting behavior. Describe the purpose and observable effect rather than listing files or copying commit subjects. Do not invent acceptance criteria, risks, tests, or links. Omit empty sections and do not repeat the title as a description heading.

Report `success`, `running`, `failed`, `canceled`, or `missing` only for a pipeline whose SHA equals the collected head SHA. Mention success only when confirmed. Report incomplete collection, unsupported raw states, and additional checks that were not verified instead of guessing.

Write the title and description in the language of the latest user request; use English when that language is ambiguous. Put exactly those two strings in the scaffold content JSON as `title` and `description`.

Create one publication plan with `scripts/prepare_mr.py scaffold --bundle <evidence-path> --content <content-path>`. Its immutable JSON envelope and Markdown companion show the current and proposed title and description with `change` or `keep`. Labels remain evidence for freshness checking; this workflow does not promise label or ownership recommendations.

Immediately before manual publication, run `scripts/prepare_mr.py finalize --plan <publication-plan-path>`. The command checks the exact evidence bound to that plan, including base/start/head SHA, object, labels, discussions, diff, commits, pipelines, and completeness. A changed, incomplete, or modified plan, Markdown companion, or evidence snapshot blocks readiness. Do not create, update, approve, merge, or push an MR.
