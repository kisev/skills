# `task-prepare`

## Purpose

Prepare self-contained work items, with optional manual GitLab publication plans.

## Triggers and Near-Misses

Trigger for preparing a task from explicit material or an agreed GitLab task set;
near-miss: review, triage, or executing publication.

## Inputs and Outputs

Neutral input is inline text, a local regular file, or an exact HTTPS link.
GitLab input may include confirmed conversation decisions and exact related
project, issue, and MR evidence. Each task has outcome, acceptance criteria,
verification, dependencies, safety, risks, and stop conditions. GitLab output is
one `task-publication.md` bundle with adjacent manual commands and body files.

## Workflow Stages

Select by intent, resolve evidence, normalize each task to `work-item/v1`, assess
semantic feasibility, resolve GitLab publication metadata when applicable,
render local artifacts, report. A GitLab source link alone keeps neutral mode.

## Dependencies

Readable explicit material and the bundled work-item contract and validator.
GitLab readiness requires read-only target, template, metadata, duplicate, and
semantic checks. Local rendering uses Python 3.12+ and the standard library.

## Remote/Local Effects

Neutral output stays in chat unless a workspace-relative output is requested.
GitLab intent automatically requests a bounded local publication bundle. New
version 2 drafts name a safe lowercase `plan_key`; the default bundle path is
`.task-prepare/<plan_key>/task-publication.md`, independent of draft content.
Identical reruns reuse the slot. Changed drafts install retained immutable support
files in a content-addressed internal directory before atomically replacing only
the stable Markdown under a slot-scoped lock. Commands name their draft's internal
payload, so later drafts cannot change the content consumed by copied commands.
Explicit workspace-relative output directories remain supported. No external
mutation or publication.

## Errors, Partial, Escalation

Missing or unreadable material blocks preparation. Unresolved semantics, targets,
or metadata remain explicit in a partial plan without creation commands for the
affected item. Missing new IIDs defer link commands; malformed input, unsafe paths,
unsafe plan keys, symlinks, concurrent slot updates, dependency cycles, and
unapproved batches fail before replacing the published Markdown. A failed
Markdown replacement leaves the prior stable plan available and may leave the
new immutable support directory retained for retry.

## Unique Constraints

The skill does not invent tracker identifiers, labels, owners, or metadata.
Project issues and supported group epics have distinct targets. Other group work
items require clarification rather than invented REST endpoints. Several tasks
require a user request or agreed split. Existing IIDs suppress creation commands;
cross-project blocking links require observed IIDs on the same instance.

## Requirement

### REQ-F-123 - Prepare one storage-neutral work item

The skill shall select neutral or GitLab output by user intent, not by a source
link alone. Neutral preparation shall accept one explicit source and return a
self-contained task in chat or an explicitly requested atomic local file.
GitLab preparation shall preserve confirmed scope, normalize each task to
`work-item/v1`, and always produce a bounded local `task-publication.md` bundle.
Multiple tasks shall require a requested or agreed split. Creation commands
shall use explicit observed targets and safe JSON file payloads only after
target, template, metadata, duplicate, and semantic checks are verified.
Unresolved targets and unsupported group APIs shall remain blocked. Dependencies
shall use real observed IIDs or remain deferred, never executable placeholders.
Existing objects shall not receive creation commands. The workflow shall never
execute publication commands or mutate GitLab. Each version 2 publication draft
shall provide a safe lowercase `plan_key`; unless an output directory is explicit,
the renderer shall retain content-addressed support files and atomically replace
only the stable Markdown after its support files are present. It shall use a
slot-scoped lock, reject symlinks and altered immutable content, and never remove
the stable plan as an update step.

## Example

`task-prepare` converts inline migration notes into a self-contained task in chat without adding tracker fields.
For an agreed cross-project migration, it creates one local plan with separate
issue commands and defers blocking-link commands until real IIDs are observed.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
