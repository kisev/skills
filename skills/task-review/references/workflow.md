# Workflow

Read `references/interaction-contract.md`, `references/gitlab-workflow.md`,
`references/portable-gitlab-contracts-v2.md`, and
`references/work-item-contract.md`. Review starts with the validator report for
the normalized item; do not mix machine and semantic findings. Always return
exactly one verdict: `ready`, `needs_clarification`, or `blocked`, along with
findings with evidence and recommended changes. The repeated verdict for an
unchanged item and evidence must be the same.

Accept one specific MR, or one or more specific Issue URL values. Do not analyze
code, architecture, security, or the full source diff; for an MR, service data,
changed files, and pipeline status are sufficient. A non-specific target requires
a Question about the boundary before the API.

Run `scripts/review_task.py prepare --url <URL>` for every explicit target in one
package. Retain an error for one item in the summary and continue with the rest.

Check only selected or all groups: `description`, `labels`, `ownership`,
`workflow`. Do not guess an assignee or reviewer. Check labels against the full
paginated list; pipeline and conflicts remain read-only evidence.

The review must describe the final state, not an action log. Account for the
reachability of criteria with known dependencies, and consistency of
outcome/scope and safety. Return `blocked` for a cyclic or unavailable
dependency.

For a complex task or explicit request, exactly one independent premortem is
permitted before review. It only proposes up to three failure causes; it does not
edit the item, and the primary agent accepts or rejects suggestions with reasons.
Without an independent agent, state `skipped` and continue the workflow.

Produce one verified Markdown plan with literal proposed title and description,
label delta, and unverified context. Before manual publication, run `finalize`;
do not publish, resolve, approve, merge, or push.
