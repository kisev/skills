# GitLab task publication

## Evidence and scope

Read GitLab through `glab` with an explicit host; inspect the installed `glab`
CLI help before choosing API flags. Authentication is needed for live evidence
and later manual publication, not for neutral preparation or local rendering.

Every publication command targets the GitLab GraphQL endpoint through
`glab api --hostname <host> --method POST graphql`. Before preparing a plan,
verify on the target instance that the required mutations are available:
`workItemCreate`, `workItemUpdate`, and `workItemAddLinkedItems` for version 3
items, `createIssue`, `createEpic`, and `updateIssue` for version 2 items.
Epics and task work items may need a licensed tier or newer GitLab version;
record observed support in the target check instead of guessing.

1. Resolve the supplied namespace URL via a read-only project/group API call;
   record its observed numeric ID and canonical HTTPS `web_url`.
   Never use the current checkout as an implicit publication target. A group
   URL does not identify a project issue destination. Inspect available group
   work-item types, permissions, and supported API on that instance; ask for
   the object type or project when needed. Do not silently substitute an epic
   for an issue.
2. Read applicable issue templates and project/group conventions; record the
   selected template or the observed absence of templates. Keep the task
   self-contained and use full URLs for existing dependencies and related work.
3. Verify selected labels (including inherited), eligible assignees, milestone
   IDs, and confidentiality. For version 3 items also observe the numeric
   label IDs next to every selected label name and the work item type global
   ID (`gid://gitlab/WorkItems::Type/<id>`) for each selected type in the
   target namespace. A ready version 2 issue requires a milestone; a version 3
   item publishes without one only when a current accepted scoped triage
   release plan records milestone status `none` with its rationale. Omit
   optional metadata without a factual basis; never create labels or assign an
   owner from a guess. Missing access or incomplete pagination is missing
   evidence, not an empty catalog.
4. Search for relevant existing issues/work items in the selected namespaces,
   including closed work when relevant; read potential matches, decide whether
   to reuse them, and record the search scope and result. An existing match
   must not yield a new creation command without an explicit reason.
5. Check task semantics against confirmed decisions; validate each normalized
   item with the work-item validator. Describe concrete verification,
   independent feature scenarios, compatibility, prerequisites, and execution
   order. Put explanatory publication notes outside the issue description.

Retain minimal read evidence privately, including the collection time and
exact target. For each check below, `verified` means the agent observed and
assessed current evidence. Use `blocked` with a concrete reason for missing,
stale, contradictory, or partial evidence; do not mark every check verified
just to obtain commands. Before resuming an old plan, refresh target, metadata,
and duplicate/link evidence rather than assuming earlier commands were
executed.

## Generate the bundle

Prepare one UTF-8 JSON input with the exact fields
`references/publication-input.md` specifies. Text is in the user's language.
The generator localizes its fixed headings for `en` and `ru`; other languages
use English fixed headings with the authored prose preserved.

Run the bundled script using its resolved installed path:

```sh
python3 scripts/prepare_publication.py --input draft.json
```

By default it creates `task-publication.md` in a workspace-scoped private slot
below `$XDG_STATE_HOME/agent-skills/task-prepare/`; optionally pass
`--output-dir <workspace-relative-directory>` for an explicit workspace bundle.
Keep the input and any explicit workspace bundle out of commits. Paths may
contain spaces; generated commands quote them. The named slot is stable across
draft changes: identical reruns reuse it; changed drafts first install
supporting files in a retained immutable `.task-publication/<content-hash>/`
directory, then atomically replace only the stable Markdown under a slot-scoped
lock. Failed Markdown replacement leaves the old plan in place, keeping
installed internal files for a retry. Unsafe keys, paths, symlinks, altered
immutable content, and concurrent updates are rejected. No preview
confirmation is needed for these local files. Changed stable plans retain
body-only content-addressed Markdown versions; the current plan ends with
paths to earlier versions; identical reruns add nothing.

Each item contains its publication text, destination, check notes, and adjacent
command when ready. Content-addressed supporting `.md` files hold only the
descriptions; `.json` files hold the exact GraphQL request with its query and
variables, including metadata. Old internal content directories are retained:
never edit or remove them while commands from their plans may still be used.
Commands use explicit
`glab api --hostname ... --method POST graphql --header 'Content-Type: application/json' --input ...`.
Do not hand-edit generated commands or payload files: edit the draft and
regenerate, keeping the preview and payload consistent.

Version 3 creations use the `workItemCreate` mutation with the observed type
ID, namespace path from the target URL, label, assignee, and milestone widgets
built from the observed numeric IDs, and the hierarchy widget for children.
Version 2 drafts stay valid and render through the `createIssue`, `createEpic`,
and `updateIssue` mutations; a version 2 draft may additionally carry the
observed `work_item_id` extension. GraphQL answers HTTP 200 even when the
request fails: the plan instructs the user to inspect the `errors` field of
every response before treating a command as executed.

## Creation and dependencies

Read `references/manual-publication.md` for the execution boundary: the user
manually runs each command at most once and inspects its response, including
the `errors` field, the new URL, IID, and the work item global ID
(`workItem { id }`); advisory markers and `execution-status` blocks never
authorize a retry. Reconcile `run_unverified` creation actions against GitLab
before adding an IID or considering any retry.

For dependencies between new tasks, the initial plan shows the intended order
and marks link commands deferred. After the user supplies creation results or
asks to resume, read the actual GitLab objects, set their `existing_iid` and
observed `work_item_id`, refresh checks, and regenerate; only then can the plan
contain executable issue-link commands: linking uses `workItemAddLinkedItems`
with `linkType: BLOCKED_BY` and needs the observed work item ID of both items.
The same two-phase rule applies to hierarchy: the parent is created first, and
children embed its work item ID once recorded. The renderer suppresses creation
for existing objects. Do not emit placeholders inside executable command blocks.
Already-present relations need no command: omit them from `links` and explain
them in check notes.

Report `partial` whenever an item is blocked or a relation is deferred. Ready
independent items may still have creation commands. The chat summary names
important blockers, explains deferred relationships, and gives the absolute
`task-publication.md` path; detailed text and commands stay in the file.
