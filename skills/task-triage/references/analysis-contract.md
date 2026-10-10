# Analysis JSON contract

This file is the field contract for the JSON analysis that `triage_task.py
publish` validates. Read it when preparing or repairing the analysis; the
runner mechanically rejects every deviation listed here, and its refusal is
the answer — never restate these checks in chat output or work around them.

Each `agent_recommendation` contains exactly `proposal`, `rationale`, `assumptions`,
`confidence`, `alternatives`, and `reconsider_if`; confidence is `low`, `medium`,
or `high`, and assumptions and alternatives are lists.

Each `issue_relations[]` contains exactly `target_hostname`, `target_project_id`,
`target_issue_iid`, `relation_type`, `rationale`, nullable `existing_link`, and
nullable `comment`. An existing link contains exactly its numeric `id` and
`relation_type`. In a REST issue-link listing, use `issue_link_id` for that
relationship ID, not `id`, which identifies the linked issue. An invalid explicit
`issue_link_id` blocks preparation; do not fall back to the issue ID. Relation type
is `relates_to`, `blocks`, or `is_blocked_by`. Its target must be an observed
different issue on the assessed issue's GitLab host. Missing relations and type
replacements correspond exactly to `proposed_changes.links[]`; extra, duplicate,
self, existing, or unobserved link proposals are invalid. An observed link
without an explicit supported type is invalid. A non-null comment has an exact
matching role-authored message on the assessed issue. Legacy `related_issues` and
`partial_relations` fields are invalid. Issue identities returned by the assessed
issue's GitLab link evidence are observed targets, including same-host issues in
another project.

Each `proposed_changes.messages[]` contains exactly `target` and `body`. Each
`information_requests[]` contains exactly `action`, `target`, `body`,
`prior_note_ids`, `rationale`, and `standalone_reason`. A target contains `kind`
(`issue` or `merge_request`), observed numeric `project_id` and `iid`, and an
observed `discussion_id` or `null` for a new standalone note. Actions are `none`,
`new`, `ping_1`, `ping_2`, `close`, or `close_fixed`; they bind respectively
zero, zero, one, two, three, or zero current-user note IDs, except `none`, which
has no publication data. A `new` action starts a standalone note with
`discussion_id=null` only when `standalone_reason` explains why no existing
discussion carries the relevant context; all other actions have
`standalone_reason=null`.

The collection-level analysis carries `top_five[]`, containing exactly
`evidence_digest` and `rationale` per entry, and `parallel_groups[]`, containing
exactly a non-empty `evidence_digests` list and `rationale` per group. Digests
are unique within each structure and bind collected items. Only accepted tasks
may appear in either structure.

Keep `questions` only for user decisions that remain unanswered after the
interaction round. Each question contains exactly `evidence_digest`, `kind`,
`tldr`, `evidence`, `decision`, `why_now`, `planning_effect`,
`recommendation`, `options`, and nullable `fallback`. Kinds are `authority`,
`private_context`, and `bounded_technical`; the latter has two or three options.
Every option has a directly selectable `label` and explanatory `description`, and
the recommendation names one option with rationale. A fallback contains exactly
`participant`, observed `target`, and `body`; its participant is an observed
non-current participant and its target/body exactly match one non-`none`
information request on the same item. It can never direct an authenticated issue
author back to themselves or exist without a manual publication command.
