# `code-review`

## Purpose

Review a local WIP or exact GitLab change for defects and contract regressions.

## Triggers and Near-Misses

Trigger for review; near-miss: preparing a merge request description.

## Inputs and Outputs

Input is one exact GitLab MR URL or the current local WIP. Remote output is a
compact role-aware assessment and a stable manual publication plan containing
ranked findings, thread actions, previous-finding dispositions, recommended
issues, exhaustive project-label applicability, a compact label delta, metadata
assessment, SemVer rationale, and digest-confirmed single-action helper commands.

## Workflow Stages

Resolve boundary, select full or GitLab-only incremental scope, inspect code and
contracts, revalidate previous findings, inspect every available project and
inherited-group label, run the critic, classify actions, and report. A separately
invoked helper follows `confirm -> revalidate -> apply one action -> verify ->
report`.

## Dependencies

Git, tests, `glab`, and GitLab evidence. Publication requires user-owned `glab`
authentication available only when the helper is invoked.

## Remote/Local Effects

Review preparation performs local reads, private immutable artifact/body writes,
one atomic pointer to the latest finalized GitLab review, and external reads for
the exact target. It never invokes publication or edits reviewed files. A user
may separately run one generated Python helper command to create or update a
discussion, issue, thread state, or exact label delta after confirming that
action's digest. The helper invokes `glab` without a shell, inherits but never
serializes the parent environment, and records an atomic private receipt.

## Errors, Partial, Escalation

Missing exact evidence or a required critic is blocked, not silently ignored.
Changed comparison boundaries, rewritten history, incompatible state, or
incomplete baseline evidence select a full review instead of partial reuse.
The publication helper rejects a missing or changed action/body digest, path
escape, actor/target/ref/catalog/thread drift, unrelated label state, ambiguous
marker, unsupported old plan, or unsafe retry. An uncertain remote mutation is
partial and never blindly repeated.

## Unique Constraints

Reviewer findings stay out of the compact chat response. Exact refs remain in
private JSON rather than user-facing reports, and artifact paths are plain
absolute paths. Publishable text carries a hidden stable ID and revision.
Incremental review is limited to GitLab MRs; local WIP is always reviewed in full.
Every GitLab body is authored from the authenticated user's factual role and
uses natural informal second person when addressing another participant. An
applicable current-line fix contains exactly one GitLab `suggestion`; other
positions use a concrete patch or replacement. Every catalog label receives one
private applicability decision; only the compact delta and unresolved/relevant
reasons appear in Markdown. One confirmation digest authorizes one action only.

## Requirement

### REQ-F-105 - Review exact changes

The skill shall distinguish one exact GitLab MR URL from local WIP, keep review
preparation non-mutating, and use a compatible finalized GitLab baseline to
review changed code, conversations, and label catalogs incrementally while
revalidating every previously accepted finding. It shall produce a compact
multilingual role-aware assessment and an action-oriented
`review-publication.md` with stable hidden publication IDs, natural
authenticated-user prose, applicable `suggestion` fixes, exhaustive private
project/inherited-label applicability with SemVer-linked compact delta, thread
reply/resolve/reopen previews, reviewer findings, non-blocking recommended
issues, and metadata/SemVer assessments. It shall encode each external write as
one closed structured action whose short Python-helper command requires that
action's digest, revalidates bounded local and live GitLab state, invokes `glab`
through inherited environment without a shell, verifies postconditions, and
recovers without duplicate publication; preparation shall never invoke it.

## Example

`code-review` maps a `major` SemVer assessment to the unique available
`semver::major`-equivalent label and prepares one confirmed label action; it
rejects an incomplete catalog or a stale action before publication.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
