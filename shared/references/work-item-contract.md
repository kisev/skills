# Shared Work Item Contract

Contract version: `work-item/v1`.

All four workflows use one normalized work item. The canonical schema and
stdlib-only validator are materialized with the document; an installed skill
does not read `shared/`.

## Normalized Structure

Required fields are `problem`, a defined `outcome`, verifiable
`acceptance_criteria`, `evidence`, and `scope` with `in_scope` and `non_goals`.
Also declare `dependencies`, `external_actions`, `assumptions`, `safety`,
`risks`, `unresolved_questions`, and `stop_conditions`.

Each dependency has an `id`, `available`, `pending`, or `blocked` status and
`depends_on`; references exist and form a DAG.

## Single Assessment

`scripts/work_item.py validate --input ITEM.json [--semantic SEMANTIC.json]`
returns JSON and a defined exit code. `machine_findings` validates form and
links; `semantic_assessment` records independent feasibility/consistency
findings. Finding order is `severity`, `code`, `path`, `message`; stable input
produces the same report and digest. Verdicts are `ready`,
`needs_clarification`, and `blocked`.

## Workflow Duties

- `askme` changes only contract fields and returns `normalized_item` or `blocker`.
- `task-prepare` creates no publication artifact before `ready` and makes no GitLab mutation.
- `task-review` returns evidence-backed findings without reviewing implementation.
- `goal` does not turn an invalid item into `running` and binds completion evidence.

## Optional Premortem

One independent pass may return at most three failures with `probability`,
`impact`, and `proposed_wording_change`. It does not edit the item; without an
independent agent the result is `skipped` and the workflow continues.
