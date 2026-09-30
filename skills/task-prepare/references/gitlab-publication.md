# GitLab task publication

## Evidence and scope

Read GitLab through `glab` with an explicit host. Inspect the installed `glab`
CLI help before choosing API flags. The
bundled generator needs only Python 3.12+ and the standard library; it never
calls GitLab. Authentication is needed for live evidence and later manual
publication, not for neutral preparation or local rendering.

Every publication command targets the GitLab GraphQL endpoint through
`glab api --hostname <host> --method POST ../graphql`. Before preparing a plan,
verify on the target instance that the required mutations are available:
`workItemCreate`, `workItemUpdate`, and `workItemAddLinkedItems` for version 3
items, `createIssue`, `createEpic`, and `updateIssue` for version 2 items.
Epics and task work items may require a licensed tier or a newer GitLab
version; record the observed support in the target check instead of guessing.

1. Resolve the supplied namespace URL with a read-only project/group API call.
   Record the observed numeric ID and canonical HTTPS `web_url`. Never use the
   current checkout as an implicit publication target. A group URL does not
   identify a project issue destination. Inspect available group work-item types,
   permissions, and supported API on that instance; ask for the object type or
   project when needed. Do not silently substitute an epic for an issue.
2. Read applicable issue templates and project/group conventions. Record the
   selected template or the observed absence of templates. Keep the task
   self-contained and use full URLs for existing dependencies and related work.
3. Verify selected labels (including inherited labels), eligible assignees,
   milestone IDs, and confidentiality. For version 3 items also observe the
   numeric label IDs next to every selected label name and the work item type
   global ID (`gid://gitlab/WorkItems::Type/<id>`) for each selected type in the
   target namespace; GraphQL sets labels and types only through these IDs.
   Milestone is mandatory for a ready version 2 issue. A version 3 item
   publishes without a milestone only when a current accepted scoped triage
   release plan records milestone status `none` with its rationale. Omit
   optional metadata without a factual basis; never create labels or assign an
   owner from a guess. Missing access or incomplete pagination is missing
   evidence, not an empty catalog.
4. Search for relevant existing issues/work items in the selected namespaces,
   including closed work when relevant. Read potential matches and decide
   whether to reuse them. Record the search scope and result. An existing match
   must not yield a new creation command without an explicit reason.
5. Check task semantics against confirmed decisions and validate each normalized
   item with the work-item validator. Describe concrete verification, independent
   feature scenarios, compatibility, prerequisites, and execution order. Put
   explanatory publication notes outside the issue description.

Retain minimal read evidence privately for this preparation, including the
collection time and exact target. For each check below, `verified` means the
agent actually observed and assessed current evidence; the renderer does not
authenticate those assertions. Use `blocked` with a concrete reason for missing,
stale, contradictory, or partial evidence. Do not mark every check verified just
to obtain commands. Before resuming an old plan, refresh target, metadata, and
duplicate/link evidence rather than assuming earlier commands were executed.

## Generate the bundle

Prepare one UTF-8 JSON input with the exact fields below. Text is in the user's
language. The generator localizes its fixed headings for `en` and `ru`; for other
languages use English fixed headings while preserving the authored prose.

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

Run the bundled script using its resolved installed path:

```sh
python3 scripts/prepare_publication.py --input draft.json
```

By default it creates `task-publication.md` in a workspace-scoped private slot
below `$XDG_STATE_HOME/agent-skills/task-prepare/`. Optionally pass `--output-dir <workspace-relative-directory>` for an explicit workspace bundle. Keep the input
and any explicit workspace bundle out of commits. Paths may contain spaces;
generated commands quote them.
The named slot is stable across draft changes. Identical reruns reuse it; changed
drafts first install supporting files in a retained immutable
`.task-publication/<content-hash>/` directory, then atomically replace only the
stable Markdown under a slot-scoped lock. The stable plan therefore never
disappears during an update, and a command copied from an older plan continues
to reference that plan's retained payload. Failed Markdown replacement leaves
the old plan in place; safely installed internal files remain for a retry. Unsafe
keys, paths, symlinks, altered immutable content, and concurrent updates are
rejected. No preview confirmation is needed for these local files.
Changed stable plans retain body-only content-addressed Markdown versions. The
current plan ends with paths to earlier versions; identical reruns add nothing.

Each item contains its publication text, destination, check notes, and adjacent
command when ready. Content-addressed supporting `.md` files hold only the
descriptions; `.json` files hold the exact GraphQL request with its query and
variables, including metadata. Old internal content directories are retained and
must not be edited or removed while commands from their plans may still be used.
Commands use explicit
`glab api --hostname ... --method POST ../graphql --header 'Content-Type: application/json' --input ...`
so the payload file carries the request verbatim. This preserves Markdown,
backticks, dollar signs, quotes, and newlines without shell interpolation. Do
not hand-edit generated commands or payload files: edit the draft and
regenerate, keeping the preview and payload consistent.

Version 3 creations use the `workItemCreate` mutation with the observed type
ID, namespace path from the target URL, label, assignee, and milestone widgets
built from the observed numeric IDs, and the hierarchy widget for children.
Version 2 drafts stay valid unchanged and render through the legacy
`createIssue`, `createEpic`, and `updateIssue` mutations, which accept label
names directly; a version 2 draft may additionally carry the observed
`work_item_id` extension. GraphQL answers HTTP 200 even when the request fails:
the plan instructs the user to inspect the `errors` field of every response
before treating a command as executed.

## Creation and dependencies

The agent stops after preparing the plan. The user manually runs each creation
command at most once and inspects its response, including the `errors` field,
the new URL, IID, and the work item global ID (`workItem { id }`). After a
timeout or lost response, inspect GitLab before retrying to avoid duplicates.
After exit zero, each mutation command writes an advisory XDG marker. The marker
does not prove that GitLab reached the expected state and never makes a retry safe.
Regenerated command blocks show `execution-status=not_run` or
`execution-status=run_unverified`. Reconcile `run_unverified` creation actions
against GitLab before adding an IID or considering any retry.

For dependencies between new tasks, the initial plan shows the intended order
and marks link commands deferred. After the user supplies creation results or
asks to resume, read the actual GitLab objects, set their `existing_iid` and
observed `work_item_id`, refresh checks, and regenerate. Only then can the plan
contain executable issue-link commands with real IDs: linking uses
`workItemAddLinkedItems` with `linkType: BLOCKED_BY` and needs the observed
work item ID of both items. The same two-phase rule applies to hierarchy: the
parent is created first, and children embed its work item ID once recorded. The
renderer suppresses creation for existing objects.
Do not treat a local file or a previously displayed command as publication proof.
Do not emit placeholders inside executable command blocks. Already-present
relations need no command: omit them from `links` and explain them in check notes.

Report `partial` whenever an item is blocked or a relation is deferred. Ready
independent items may still have creation commands. The chat summary names
important blockers, explains deferred relationships, and gives the absolute
`task-publication.md` path; detailed text and commands stay in the file.
