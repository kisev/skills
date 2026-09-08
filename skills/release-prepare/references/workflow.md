# Release MR preparation

Read `references/interaction-contract.md`, `references/gitlab-workflow.md`, `references/portable-gitlab-contracts-v2.md`, and `references/language-policy.md`. Accept one exact MR URL. Record the previous tag or explicitly selected previous boundary, exact base/start/head SHA, and exact commit range. Do not call inventory complete after a pagination error, incomplete range, or unavailable MR.

Verify release contents, direct commits, linked issues, the pipeline for the exact SHA, compatibility, migrations, configuration, and defaults. Choose SemVer from observable contracts; do not claim backward compatibility without evidence.

Prepare the title, description, and announcement in the language of the latest user request; use English when that language is ambiguous. Prepare an English illustration prompt with no text or logos. Do not choose a Mattermost channel or send a message: the announcement remains a separate explicit user action. Produce one Markdown plan and recheck freshness through `finalize` before manual publication.

Read `references/interaction-contract.md`, `references/gitlab-workflow.md`, `references/portable-gitlab-contracts-v2.md`, and `references/language-policy.md`. Accept one exact MR URL. Record the previous tag or explicitly selected previous boundary, the exact base/start/head SHA, and the exact commit range. Do not call the inventory complete on a pagination error, incomplete range, or unavailable MR.

Check release contents, direct commits, related tasks, the pipeline for the exact SHA, compatibility, migrations, configuration, and default values. Choose SemVer by observable contracts; do not claim backward compatibility without evidence.

Prepare the title, description, and announcement in the language of the latest user request; use English when that language is ambiguous. Prepare an English illustration prompt without text or logos. Do not select a Mattermost channel or send the message: the announcement remains a separate explicit user action. Create one Markdown plan and recheck currency through `finalize` before manual publication.
