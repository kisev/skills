# Publication bundle input (version 3)

This file is the field contract for the UTF-8 JSON input that
`scripts/prepare_publication.py` consumes. Read it when preparing or repairing a
publication draft; the generator and its validator mechanically reject every
deviation listed here.

```json
{
  "version": 3,
  "plan_key": "bedrock-plan",
  "locale": "en",
  "batch_agreement": "The user agreed to the parent issue with child tasks split.",
  "items": [
    {
      "key": "parent-issue",
      "title": "Bedrock umbrella",
      "description": "Self-contained Markdown task with acceptance criteria and verification.",
      "target": {
        "kind": "project",
        "id": 29128,
        "url": "https://gitlab.example.org/devops/ci/meta"
      },
      "type": "issue",
      "metadata": {
        "labels": ["team::pipelines"],
        "label_ids": [1044]
      },
      "checks": {
        "target": { "status": "blocked", "detail": "Select the destination project." },
        "templates": { "status": "blocked", "detail": "Destination is not resolved." },
        "metadata": { "status": "blocked", "detail": "Destination is not resolved." },
        "duplicates": { "status": "blocked", "detail": "Destination is not resolved." },
        "semantics": { "status": "blocked", "detail": "Verify the agreed feature scenarios." }
      },
      "existing_iid": null,
      "parent": null,
      "initial_state": "open",
      "work_item_id": null,
      "work_item_type_id": null
    }
  ],
  "links": []
}
```

- `batch_agreement`: empty for one task, otherwise quote or summarize the user's
  request for multiple tasks or agreement to this split. Do not infer approval
  from the number of repositories.
- `plan_key`: stable lowercase identifier for this publication plan, up to 64
  characters, using letters, digits, and hyphens and starting with a letter. It
  selects the default local slot and must not be derived from draft content.
- `key`: unique lowercase identifier, up to 64 characters, letters, digits, hyphens,
  starting with a letter. `task-publication` and `link-<number>` are reserved for
  bundle artifacts. It is local bookkeeping, never a fabricated GitLab ID.
- `target`: `null` when unresolved, otherwise
  `{"kind":"project","id":123,"url":"https://gitlab.example.org/team/project"}`.
  A group uses `kind: "group"` and `/groups/team/subgroup` in its URL.
- `type`: version 3 accepts `issue`, `task`, and `epic`; version 2 accepts only
  `issue` and `epic`. Issues and tasks require project targets; epics require
  groups. Group epic creation needs the instance's work item API for the epic
  type; other group work-item types stay blocked until their API is confirmed.
- `metadata`: optional `labels` (observed names without commas), `label_ids`
  (observed numeric label IDs, one per name, version 3 only), `assignee_ids`
  (numeric IDs), `milestone_id` (numeric ID), `confidential` (boolean).
  `milestone_id` is required for every ready version 2 issue and must equal the
  selected observed milestone in the scoped release plan; version 3 omits it
  only from an accepted milestone status `none` decision. Epics support only
  labels and confidentiality in this renderer. Explain unsupported requested
  fields instead of silently dropping them.
- `existing_iid`: observed IID for a reused or already created object, otherwise
  `null`. With an IID the renderer omits creation and emits only the required
  milestone assignment update; it does not rewrite title or description.
- `parent`: version 3 only; `null` or the key of another plan item of type
  `issue` or `task` on the same host. The renderer embeds the observed parent
  work item ID into the child creation; until the parent has one, the child
  creation stays deferred.
- `initial_state`: version 3 only; `open` (default) or `closed`. A closed item
  is created normally, and its close command appears after its observed work
  item ID is recorded. When an observed item is already closed, remove the
  closed initial state instead of emitting a redundant command.
- `work_item_id`: `null` or the observed global ID
  `gid://gitlab/WorkItem/<id>` of an existing object. Version 2 items accept it
  as an optional extension for link commands; version 3 uses it for hierarchy,
  close, and non-issue milestone commands.
- `work_item_type_id`: version 3 only; `null` or the observed
  `gid://gitlab/WorkItems::Type/<id>` for the item type in the target
  namespace. A ready version 3 creation requires it.
- `checks`: exactly `target`, `templates`, `metadata`, `duplicates`, `semantics`;
  each has `status` (`verified` or `blocked`) and nonempty `detail` containing
  evidence or a concrete blocker. Target evidence also verifies type, API support,
  and any existing IID. Metadata details list selected values and their rationale.
- `links`: dependencies as
  `{"source":"consumer","target":"prerequisite","rationale":"Why it blocks","verified":false}`.
  Both keys must be in the plan; dependencies must be acyclic. `verified` means
  the agent checked support for issue blocking links and that the relation is
  not already present. Group hierarchy and cross-host links are not silently
  converted to project issue links.
