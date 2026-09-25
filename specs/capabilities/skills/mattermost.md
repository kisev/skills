# `mattermost`

## Purpose

Read a bounded Mattermost post, thread, channel, or chat from an exact URL, or
prepare a manual plan for publishing messages to exact Mattermost targets.

## Triggers and Near-Misses

Trigger for Mattermost reading and message sending. A send request produces a
manual publication plan; the skill never invokes its generated apply or inspect
commands. Near-misses are broad search and edit, delete, reaction, channel, or
member mutations.

## Inputs and Outputs

Read input is one exact URL and bounded period or scope. Publication preparation
accepts JSON stdin with `messages[{target,message,files}]`: exact HTTPS targets on
one origin and zero to five absolute regular source files per message, each at
most 100 MiB. Output is redacted read evidence or a stable private XDG manual
publication plan.

## Workflow Stages

Resolve an exact URL or exact current Mattermost context without broad search.
Reading and preparation use GET only. Preparation freezes immutable actions,
bodies, and history, then presents one digest-confirmed manual command per
message. The separately invoked helper revalidates and may upload zero to five
files before creating one post as one compound user-visible action.

## Dependencies

Mattermost read and bounded publication APIs, origin-bound credentials, private
XDG state, source files, and cache policy.

## Remote/Local Effects

Exact external GET reads; local cache and publication-plan state may be used.
Preparation never mutates Mattermost. A separately and manually invoked helper
may issue bounded POST requests to upload files and create exactly one post for
one action digest; the skill itself never invokes apply or inspect. Channel or
chat intervals wholly older than seven days are intentionally treated as
immutable and reused without freshness expiry. This is a deliberate
performance/freshness tradeoff: it avoids repeated historical API reads, but
late edits or deletes remain stale until an explicit `--refresh`.

## Errors, Partial, Escalation

Auth, pagination, or repeated-page failures produce partial or blocked status.
Publication progress is durable. An ambiguous upload blocks retry and may leave
an unattached server file; an ambiguous post requires manual inspect and is never
replayed by the agent.

## Unique Constraints

Origin binding, secret redaction, exact URL resolution, and one-channel
membership boundaries apply. Authentication offers a recommended consented
browser flow, validated by exact-origin `/users/me` before save, or a manual raw
token file discovered with `auth path URL`. Token directories are mode `0700`;
the raw-token-plus-newline file is owner-owned, regular, singly linked, and mode
`0600`. Tokens never enter argv or chat.

Publication source files are not copied and must match their recorded size and
SHA-256 at apply time. The created post uses hidden
`props.agent_skill_publication_id` without a visible marker. One action digest
authorizes one message, although that message may require zero to five uploads
and one post as a single compound action. Edit, delete, reaction, channel, and
member mutations remain excluded.
Unrefreshed stable cache can retain and return content that was later edited or
deleted, including for security or compliance reasons; callers shall use
`--refresh` whenever the current redaction or deletion state matters.

## Requirement

### REQ-F-113 - Read and prepare Mattermost publication safely

The skill shall perform bounded GET reads, preserve safe evidence on partial
failure, and prepare digest-bound manual message publications without invoking
their apply or inspect commands. Only the separate helper may perform bounded
POST requests for one confirmed message action.

## Example

`mattermost` reads a thread URL and marks an incomplete repeated page as partial,
or prepares one manual command for a message with attachments without sending it.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
