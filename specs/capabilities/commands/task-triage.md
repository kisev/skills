# `/task-triage`

## Purpose

Expose bounded GitLab issue and issue-collection triage.

## Triggers and Near-Misses

Route one issue, an explicit issue list, or a filtered project collection; near-miss: task drafting or implementation.

## Inputs/Outputs

Arguments identify exact GitLab issue or project collection URLs, optional
filters, and the selected `en` or `ru` locale. Output names the localized stable
XDG summary, per-issue reports, completeness, cache disposition, planning
decisions, release milestones, consolidated questions, and separate manual
commands for each proposed GitLab action.

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

## Example

`/task-triage https://gitlab.example/group/project/-/issues` triages open issues,
reuses current per-issue analysis, and returns the stable summary path.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
