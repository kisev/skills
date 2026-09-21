# `/release-prepare`

## Purpose

Expose preparation and read-only refresh of one stable release runbook.

## Triggers and Near-Misses

Routes exact release MR; near-miss: release review.

## Inputs/Outputs

Arguments identify the exact release MR and boundary. Output is one stable,
target-scoped `release-publication.md` with immutable payloads and manual commands.

## Workflow Stages

Select, collect, decide, draft, finalize, and report. A post-merge invocation
refreshes the same runbook after verifying the exact merged MR and commit.

## Dependencies

`release-prepare`, Git evidence, and GitLab read access.

## Remote/Local Effects

Read-only collection and atomic local runbook replacement. Neither the command nor
its helper executes `glab` mutations, merge, release, comment, or work-item actions.

## Errors/Partial/Escalation

Missing exact boundary, complete component MR evidence, merge state, CI, or a
required interactive decision is blocking. Changed bindings make the runbook stale.

## Unique Constraints

The runbook contains manual `glab` commands only. Pre-merge commands cover the
milestone, MR update, announcement and prompt attachment, and merge. Post-merge
commands cover the release and approved item actions; release notes exactly match
the MR description.

## Requirement

### REQ-I-215 - Route the release-prepare command

The command shall load exactly `release-prepare`, report only its stable
user-facing runbook path, and perform no remote mutation. Commands in the runbook
shall consume immutable payloads and bind the exact host, project, MR, SHA,
milestone, release, and work item as applicable.

## Example

`/release-prepare` prepares or refreshes the stable release runbook without running
its commands.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
