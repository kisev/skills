# Release MR review

Read `references/interaction-contract.md`, `references/gitlab-workflow.md`, and `references/portable-gitlab-contracts-v2.md`. Accept one exact MR URL; without one, ask for the link. Do not create a worktree or modify the repository, MR, issue, release, pipeline, or any other external system.

Check collection completeness, exact head SHA, version, changelog, release contents, breaking changes, migrations, update notes, rollback, release artifacts, and the pipeline for the exact SHA. Verify material claims against the diff, target branch, and linked issues. Report only confirmed findings with evidence, consequence, and the minimum fix.

The result contains verdict `ready`, `not_ready`, or `blocked`, boolean readiness, and gates `semver`, `compatibility`, `migration`, `rollback`, `ci`. Every gate contains verified status, inputs, and evidence. With incomplete or changed target, verdict is only `blocked`. Do not publish comments, approval, labels, or status.

Read `references/interaction-contract.md`, `references/gitlab-workflow.md`, and `references/portable-gitlab-contracts-v2.md`. Accept one exact MR URL; without it, request the link. Do not create a worktree or modify the repository, MR, issue, release, pipeline, or another external system.

Check collection completeness, the exact head SHA, version, changelog, release contents, breaking changes, migrations, update notes, rollback, release artifacts, and the pipeline for the exact SHA. Check material claims against the diff, target branch, and related tasks. Report only confirmed findings with evidence, consequence, and the minimal fix.

The outcome contains verdict `ready`, `not_ready`, or `blocked`, Boolean readiness, and gates `semver`, `compatibility`, `migration`, `rollback`, `ci`. Each gate contains verified status, inputs, and evidence. With an incomplete or changed target, the verdict is only `blocked`. Do not publish comments, approval, labels, or status.
