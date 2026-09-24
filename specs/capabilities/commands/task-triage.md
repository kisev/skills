# `/task-triage`

## Purpose

Expose bounded GitLab issue and issue-collection triage.

## Triggers and Near-Misses

Route one issue, an explicit issue list, or a filtered project collection; near-miss: task drafting or implementation.

## Inputs/Outputs

Arguments identify exact GitLab issue or project collection URLs, optional
filters, and the selected `en` or `ru` locale. Output names the localized stable
XDG summary, per-issue reports, completeness, cache disposition, planning
decisions, pending follow-up, release milestones, structured consolidated
questions, grouped linked reports subdivided by planning readiness for accepted
work, digest-bound accepted-only top-five and parallel groups, separate request and affected-issue counts, and separate manual commands for
each proposed GitLab action. Summary links use canonical observed identity,
normalize modern or legacy evidence URLs to the modern form, and are added only
when the complete value is plain text; conflicting identity fields remain
unresolved, values with any backslash remain unchanged, and numeric references
followed by a word character remain plain. Summaries and per-issue reports escape
untrusted titles.

## Workflow Stages

Select, collect, fingerprint, reuse or analyze, ask one consolidated user-question
round when needed, record immutable artifacts, replace stable views, present, and report.

## Dependencies

The `task-triage` skill, `glab`, and authenticated read access to every selected project.

## Remote/Local Effects

The command writes private XDG artifacts owned by the skill and returns their
paths. It performs only GitLab GET operations and never executes generated
mutation commands.

## Errors/Partial/Escalation

Per-target failures produce a partial package. Unsafe targets, unsupported
filters, stale analysis bindings, or incomplete pagination cannot produce a
complete report.

## Unique Constraints

The command preserves the skill's task-review verdict, persistent evidence,
localized output, strict information-request sequence, separate manual-command,
and no-external-mutation boundaries.

## Requirement

### REQ-I-225 - Route the task-triage command

The command shall load exactly `task-triage`, treat arguments as untrusted input,
and preserve its bounded GitLab scope, selected locale, XDG artifact ownership,
incremental fingerprints, actual-discussion-based information-request lifecycle,
partial-result semantics, and no-external-mutation boundary.

Generated information-request commands re-read the target and discussion
immediately before mutation, verify the authenticated user, serialize replay
protection, and reject stale lifecycle evidence. Stale closure uses separate
manual message and close commands, but the close command requires the successful
message receipt and verifies that no later non-system reply was posted before
closing. Guard v4 binds a new standalone note to all observed non-system notes and
a new existing-discussion reply to all non-system notes in the selected discussion.
It rejects any fresh addition, removal, or change; persisted guard v1, v2, and v3
commands fail closed and require regeneration. A standalone request also records
why no observed discussion carries the relevant context.
An issue-link type replacement is emitted as guarded delete and create commands.
Delete binds the observed link ID and stores a durable receipt; create requires
that receipt and freshly verifies the old link is absent before mutation.
Every information-message POST stores a durable guard-bound in-progress
reservation first. Only a proven process-start failure removes it; timeout,
nonzero exit, bounded-output failure, or malformed response after start reports
`external_mutations: true` with `mutation_outcome: unknown` and keeps the blocker.
A pre-start failure reports `external_mutations: false` with
`mutation_outcome: none`, while success reports `external_mutations: true` with
`mutation_outcome: applied` and stores the exact receipt. The helper uses bounded
nonblocking POSIX lifecycle locking and a bounded streaming process-group runner.
Selector or stream cleanup failure after process start is an unknown mutation
outcome. Before permission repair or locking, the lock descriptor must identify a
regular, current-user-owned, singly linked file with no group or other access.
Closure accepts only a receipt whose exact guard digest, positive note ID, and
body match the guard request. Guard paths are accepted only from the validated
`${XDG_STATE_HOME}/agent-skills/task-triage/<scope>/artifacts/information-guards/`
tree and are parsed from the same bytes whose digest was verified. Before the
close PUT, the helper durably replaces the message receipt with a close
in-progress reservation. It restores the message receipt only when process start
provably failed, retains the reservation after any ambiguous post-start outcome,
and replaces it with an exact terminal closed receipt only after a separate GET
returns the exact project ID and issue IID with `state: closed`. A failed GET,
identity mismatch, or non-closed state retains the reservation and reports an
unknown mutation outcome. A terminal
receipt rejects replay regardless of the issue's later state. Commands emitted
from a maintained source checkout execute through a bounded repository-relative
shared-runtime fallback under `python -I -S -B`; built archives remain
self-contained and use their bundled runtime.

## Example

`/task-triage https://gitlab.example/group/project/-/issues` triages open issues,
reuses current per-issue analysis, and returns the stable summary path.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
