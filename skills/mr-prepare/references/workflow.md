# Ordinary MR preparation

Read `references/interaction-contract.md`, `references/gitlab-workflow.md`, and `references/portable-gitlab-contracts-v2.md`. Accept only one exact MR URL; do not create a batch. The runner collects metadata, changed files, the pipeline for the exact head SHA, and the complete paginated label list.

Verify the title and description against the verifiable diff, commits, linked issues, and project templates. Do not invent criteria, risks, tests, or links in the description. Mention successful checks only with confirmed status. Explicitly list incomplete collection and unverified additional checks.

Prepare one Markdown plan with title, description, label changes, and ownership. Before manual publication, run `scripts/prepare_mr.py finalize --artifact-root <path>`: changed base/start/head SHA, object, labels, discussions, diff, pipeline, or completeness block the plan. Do not create, update, approve, merge, or push an MR.

Read `references/interaction-contract.md`, `references/gitlab-workflow.md`, and `references/portable-gitlab-contracts-v2.md`. Accept only one specific MR URL; do not create a batch. The runner collects metadata, changed files, the pipeline for the exact head SHA, and the full paginated label list.

Check the title and description against the verifiable diff, commits, related tasks, and project templates. Do not invent criteria, risks, tests, or links in the description. Mention successful checks only with confirmed status. Explicitly list incomplete collection and unverified additional checks.

Prepare one Markdown plan with the title, description, label change, and ownership. Before manual publication, run `scripts/prepare_mr.py finalize --artifact-root <path>`: a changed base/start/head SHA, object, labels, discussions, diff, pipeline, or completeness blocks the plan. Do not create, update, approve, merge, or push the MR.
