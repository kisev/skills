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
assessment, SemVer rationale, validated per-item suggestions or unified patches,
and direct manual `glab` commands that consume generated body files.

## Workflow Stages

Resolve boundary, select full or GitLab-only incremental scope, inspect code and
contracts, revalidate previous findings, inspect every available project and
inherited-group label, record the critic when required, finalize evidence and the
decision, scaffold a contract-4 plan, and render chat from that plan. The runner
exposes the current stage and exact next action so interrupted reviews can resume
without guessing. Publication remains a separate manual step through the direct
`glab` commands shown in the plan.

## Dependencies

Git, tests, `glab`, and GitLab evidence. Manual publication requires user-owned
`glab` authentication.

## Remote/Local Effects

Review preparation performs local reads, writes private immutable artifacts,
bodies, and validated patches, maintains one atomic pointer to the latest
finalized GitLab review, and reads external state for the exact target. It never
invokes publication or edits reviewed files. The plan instead gives the user
direct manual `glab` commands for each discussion, issue, thread-state, or label
change and the body file consumed by that command.

## Errors, Partial, Escalation

Missing exact evidence or a required critic is blocked, not silently ignored.
Missing or stale context, critic, finalize, decision, content, plan, baseline, or
Markdown bindings make the final report blocked; findings are never reported as
a best-effort substitute. A failed exact-head pipeline without a blocking
finding requires an owner decision, while low findings are non-blocking.
Irrecoverable loss of the current evidence remains blocked without a synthesized
next action because the target can no longer be trusted.
Changed comparison boundaries, rewritten history, incompatible state, or
incomplete baseline evidence select a full review instead of partial reuse.
Incremental publication assessment reads actual GitLab discussions, notes, and
issues authored by the current `glab` user and compares their meaning to the
review content. It does not use local receipts, markers, idempotency records, or
postconditions.

## Unique Constraints

Reviewer findings stay out of the compact chat response. Exact refs remain in
private JSON rather than user-facing reports, and artifact paths are plain
absolute paths.
Incremental review is limited to GitLab MRs; local WIP is always reviewed in full.
Every GitLab body is authored from the authenticated user's factual role and
uses natural informal second person when addressing another participant. An
applicable current-line fix contains exactly one single-line or bounded
multi-line GitLab `suggestion`; other actionable findings, thread corrections,
and author local fixes use one validated unified patch per item. Threads without
a code correction explicitly use `not_required`. Every catalog label receives one
private applicability decision; only the compact delta and unresolved/relevant
reasons appear in Markdown.

## Requirement

### REQ-F-105 - Review exact changes

The skill shall distinguish one exact GitLab MR URL from local WIP, keep review
preparation non-mutating, and use a compatible finalized GitLab baseline to
review changed code, conversations, and label catalogs incrementally while
revalidating every previously accepted finding. It shall produce a compact
multilingual role-aware assessment and an action-oriented
`review-publication.md` with natural authenticated-user prose, applicable
`suggestion` fixes, exhaustive private
project/inherited-label applicability with SemVer-linked compact delta, thread
reply/resolve/reopen previews, reviewer findings, non-blocking recommended
issues, and metadata/SemVer assessments. Every actionable finding, thread
correction, and author local fix shall contain either one exact-position
single-line or bounded multi-line suggestion or one content-addressed textual
unified patch validated against the exact reviewed head without changing the
checkout; a thread without a code correction shall explicitly use
`not_required`, and every open thread shall use an explicit reply, closure, or
author local-fix outcome rather than `no_publication`. It shall prepare direct
manual `glab` commands with explicit body files and shall not track command
execution, publication receipts, hidden markers, retries, or postconditions;
preparation shall never invoke those commands. For remote review, the runner shall own a resumable fail-closed state
machine from prepared evidence through a recorded independent critic when the
selected mode requires one, fresh finalize report, bound decision, contract-4
plan, baseline, Markdown, and final chat rendering. It shall generate model-ready critic, decision, and content
templates with exact artifact, label, thread, latest-note, and pipeline bindings;
reject out-of-order, incomplete, stale, or structurally duplicate accepted findings and plans; keep reviewer finding details
out of chat; treat low findings as non-blocking; and render a failed exact-head
pipeline without another blocking finding as owner decision required.

## Example

`code-review` maps a `major` SemVer assessment to the unique available
`semver::major`-equivalent label and prepares one manual label command; it
rejects an incomplete catalog before plan creation.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
