# GitLab task publication

## Evidence and scope

Read GitLab through `glab` with an explicit host. Inspect the installed `glab`
CLI help before choosing API flags. The
bundled generator needs only Python 3.12+ and the standard library; it never
calls GitLab. Authentication is needed for live evidence and later manual
publication, not for neutral preparation or local rendering.

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
   milestone IDs, and confidentiality. Milestone is mandatory for a ready issue
   plan and must come from a current accepted scoped triage release plan. Omit optional metadata without a factual
   basis; never create labels or assign an owner from a guess. Missing access or
   incomplete pagination is missing evidence, not an empty catalog.
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
  "version": 2,
  "plan_key": "configuration-contract",
  "locale": "en",
  "batch_agreement": "",
  "items": [
    {
      "key": "align-contract",
      "title": "Align the configuration contract",
      "description": "Self-contained Markdown task with acceptance criteria and verification.",
      "target": null,
      "type": "issue",
      "metadata": {},
      "checks": {
        "target": { "status": "blocked", "detail": "Select the destination project." },
        "templates": { "status": "blocked", "detail": "Destination is not resolved." },
        "metadata": { "status": "blocked", "detail": "Destination is not resolved." },
        "duplicates": { "status": "blocked", "detail": "Destination is not resolved." },
        "semantics": { "status": "blocked", "detail": "Verify the agreed feature scenarios." }
      },
      "existing_iid": null
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
- `type`: `issue` for a project or `epic` for a group. Group epic commands are
  available only after confirming the user's intended type and that the instance
  supports `POST groups/:id/epics`. Other group work-item types remain blocked:
  explain the unsupported API and agree a supported target/type; never invent
  `groups/:id/issues` or a REST `work_items` endpoint.
- `metadata`: optional `labels` (observed names without commas), `assignee_ids`
  (numeric IDs), `milestone_id` (numeric ID), `confidential` (boolean).
  `milestone_id` is required for every ready issue and must equal the selected
  observed milestone in the scoped release plan. Epics
  support only labels and confidentiality in this renderer. Explain unsupported
  requested fields instead of silently dropping them.
- `existing_iid`: observed IID for a reused or already created object, otherwise
  `null`. With an IID the renderer omits creation and emits only the required
  milestone assignment update; it does not rewrite title or description.
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
descriptions; `.json` files hold the exact API requests including metadata.
Old internal content directories are retained and must not be edited or removed
while commands from their plans may still be used. Commands use explicit
`glab api --hostname ... --method POST ... --input ...` with a JSON content type.
This preserves Markdown, backticks, dollar signs, quotes, and newlines without
shell interpolation. Do not hand-edit generated commands or payload files:
edit the draft and regenerate, keeping the preview and payload consistent.

## Creation and dependencies

The agent stops after preparing the plan. The user manually runs each creation
command at most once and inspects its response, including the new URL and IID.
After a timeout or lost response, inspect GitLab before retrying to avoid duplicates.
After exit zero, each mutation command writes an advisory XDG marker. The marker
does not prove that GitLab reached the expected state and never makes a retry safe.
Regenerated command blocks show `execution-status=not_run` or
`execution-status=run_unverified`. Reconcile `run_unverified` creation actions
against GitLab before adding an IID or considering any retry.

For dependencies between new tasks, the initial plan shows the intended order
and marks link commands deferred. After the user supplies creation results or
asks to resume, read the actual GitLab objects, set their `existing_iid`, refresh
checks, and regenerate. Only then can the plan contain executable issue-link
commands with real IDs. The renderer suppresses creation for existing objects.
Do not treat a local file or a previously displayed command as publication proof.
Do not emit placeholders inside executable command blocks. Already-present
relations need no command: omit them from `links` and explain them in check notes.

Report `partial` whenever an item is blocked or a relation is deferred. Ready
independent items may still have creation commands. The chat summary names
important blockers, explains deferred relationships, and gives the absolute
`task-publication.md` path; detailed text and commands stay in the file.
