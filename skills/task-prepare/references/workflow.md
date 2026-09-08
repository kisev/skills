# Workflow

Read `references/interaction-contract.md`, `references/gitlab-workflow.md`,
`references/portable-gitlab-contracts-v2.md`, and
`references/work-item-contract.md`, and `references/language-policy.md`. First normalize the work item and run
`scripts/work_item.py validate`. A publication artifact is allowed only with
verdict `ready`; return `needs_clarification` and `blocked` without preparing a
publication result. GitLab mutations remain forbidden. Choose exactly one mode:
`update` for one existing issue, `create` for one new issue, or `batch` for an
explicit set of new issues. Do not switch modes by guesswork.

Before collection, show the **Assumed task**: problem, expected result, boundary,
acceptance criteria, and open questions. Ask only missing questions through the
host mechanism or in chat. This is resolution, not Confirmation: private
read-only evidence and a plan may be prepared without confirmation.

The normalized item must also include dependencies, external actions,
assumptions, safety/operational constraints, risks, and stop conditions. The
agent evaluates semantic feasibility and returns the same structured report as
the machine validator.

Write the title and description in the language of the latest user request; use
English when that language is ambiguous.

In `update`, use a specific Issue URL. In `batch`, first clarify every new issue,
its boundary, criteria, and dependency DAG with questions only when decisions are
missing. An error in one package item does not cancel the other items.

The runner prepares an immutable evidence envelope and a local Markdown plan;
verify all labels through full pagination. Do not assign an assignee by default.
Batch dependencies remain a manual plan until real IID values exist. Do not
create or update GitLab issues.
