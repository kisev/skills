# `code-review`

## Purpose

Review a local WIP or exact GitLab change for defects and contract regressions.

## Triggers and Near-Misses

Trigger for review; near-miss: preparing a merge request description.

## Inputs and Outputs

Input is one exact GitLab MR URL or the current local WIP. Remote output is a
compact role-aware assessment and a stable manual publication plan containing
ranked findings, thread actions, previous-finding dispositions, recommended
issues, metadata assessment, and SemVer rationale.

## Workflow Stages

Resolve boundary, select full or GitLab-only incremental scope, inspect code and
contracts, revalidate previous findings, run the critic, classify actions, and
report.

## Dependencies

Git, tests, and optional GitLab read-only evidence.

## Remote/Local Effects

Local reads, private immutable artifact/body writes, and one atomic pointer to
the latest finalized GitLab review; external reads only for exact review
targets. The skill may prepare manual GitLab discussion and issue commands but
never executes external writes or edits reviewed files.

## Errors, Partial, Escalation

Missing exact evidence or a required critic is blocked, not silently ignored.
Changed comparison boundaries, rewritten history, incompatible state, or
incomplete baseline evidence select a full review instead of partial reuse.

## Unique Constraints

Reviewer findings stay out of the compact chat response. Exact refs remain in
private JSON rather than user-facing reports, and artifact paths are plain
absolute paths. Publishable text carries a hidden stable ID and revision.
Incremental review is limited to GitLab MRs; local WIP is always reviewed in full.

## Requirement

### REQ-F-105 - Review exact changes

The skill shall distinguish one exact GitLab MR URL from local WIP, keep local
review full and read-only, and use a compatible finalized GitLab baseline to
review changed code and conversations incrementally while revalidating every
previously accepted finding. It shall produce a compact multilingual role-aware
assessment and an action-oriented `review-publication.md` with stable hidden
publication IDs, thread reply/resolve/reopen previews, reviewer finding
previews, non-blocking recommended issues, metadata and SemVer assessments, and
private-exact-ref preflight commands without executing them.

## Example

`code-review` rejects a changed incremental review when its delta-bound
independent critic receipt is absent.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
