# Ordinary MR preparation

Read `references/interaction-contract.md`, `references/gitlab-workflow.md`, `references/portable-gitlab-contracts-v2.md`, `references/label-semantics.md`, and `references/language-policy.md`. Accept only one exact MR URL; do not infer an MR from a branch and do not create a batch. The runner collects metadata, changed files, commits, discussions, pipelines for the exact head SHA, and the complete paginated project and inherited-group label catalog.

Verify the title and description against the collected diff, commits, discussions, and linked context that is actually available. Use project templates only when they are already available in the local checkout or collected evidence; do not widen collection to fetch templates, linked issues, `AGENTS.md`, or CONTRIBUTING. Explicitly list unavailable context.

Write a title of 5-10 words that states the resulting behavior. Describe the purpose and observable effect rather than listing files or copying commit subjects. Do not invent acceptance criteria, risks, tests, or links. Omit empty sections and do not repeat the title as a description heading.

Report `success`, `running`, `failed`, `canceled`, or `missing` only for a pipeline whose SHA equals the collected head SHA. Mention success only when confirmed. Report incomplete collection, unsupported raw states, and additional checks that were not verified instead of guessing.

Write the title and description in the language of the latest user request; use English when that language is ambiguous. Derive semantic label intent from verified evidence, not organization-specific names. Leave urgency, impact, origin, compatibility, or workflow state as `null` when the evidence does not support a value.

Put exactly `title`, `description`, and `label_intent` in the scaffold content JSON. `label_intent` contains every role from `label-semantics.md` and semantic values or `null`, never concrete label names. Create one publication plan with `scripts/prepare_mr.py scaffold --bundle <evidence-path> --content <content-path>`. Its immutable JSON envelope and Markdown companion show title and description changes plus a read-only label table with `current`, `proposed`, `add`, `remove`, and per-role reasons. Unknown labels are preserved; absent semantics are unsupported no-ops, while ambiguous mappings remain unresolved.

Immediately before manual publication, run `scripts/prepare_mr.py finalize --plan <publication-plan-path>`. The command checks the exact evidence bound to that plan, including base/start/head SHA, object, label catalog and current labels, discussions, diff, commits, pipelines, and completeness. A changed, incomplete, unresolved, or modified plan, Markdown companion, or evidence snapshot blocks readiness. Do not create, update, approve, merge, push, or mutate labels.
