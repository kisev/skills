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
and direct manual `glab` commands that consume generated body files. Published
patches are copy-ready `git apply` heredocs, while explanation and thread-state
commands remain separate.
The human publication plan identifies the skill and review-contract versions,
keeps label delta beside compact MR metadata, and omits internal action IDs,
operations, positions, body paths, and digests.

## Workflow Stages

Resolve boundary, select full or target-specific incremental scope, inspect code and
contracts, revalidate previous findings, inspect every available project and
inherited-group label, record the critic when required, finalize evidence and the
decision, scaffold a contract-6 plan, and render chat from that plan. The runner
exposes the current stage and exact next action so interrupted reviews can resume
without guessing. Publication remains a separate user-invoked step governed by
the requirement below.

## Dependencies

Git, tests, `glab`, and GitLab evidence. Manual publication requires user-owned
`glab` authentication.

## Remote/Local Effects

Review preparation performs local reads, writes private immutable artifacts,
bodies, and validated patches, maintains one atomic pointer to the latest
finalized GitLab review, and reads external state for the exact target. It never
invokes publication or edits reviewed files. The plan instead gives the user
one-action guarded commands for discussion, issue, thread-state, or label changes
and their exact body previews.

## Errors, Partial, Escalation

Missing exact evidence, complete MR-bound exact-head job metadata, required
failed-job trace excerpts with HTTP-confirmed range completeness, or a required
critic is blocked, not silently ignored.
Missing or stale context, critic, finalize, decision, content, plan, baseline, or
Markdown bindings make the final report blocked; findings are never reported as
a best-effort substitute. Failed/canceled jobs are classified from bounded,
redacted trace evidence across child/downstream pipelines rather than from job
names. Only clearly proven approval or equivalent manual process gates may avoid
blocking `ready`; code, infrastructure, unknown, and incomplete failures remain
blocking, while low findings are non-blocking.
Job-trace collection shall stream response headers and content under one bounded
deadline and hard byte limit, clean up and reap the process group within bounded
waits on every exit, and fail with a controlled error when cleanup or the
required POSIX capability is unavailable.
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
Local WIP uses a separate finalized report and snapshot baseline; its repeated
review defaults to fix verification and delta-triggered analysis of affected
consumers. GitLab publication artifacts are not created for local WIP.
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
issues, and metadata/SemVer assessments. Contract-6 plans shall distinguish the
MR's own SemVer contribution (which selects its compatibility label) from the
accumulated next-release impact after including the MR. The reviewer shall
establish publication policy and the last published release of the affected
line from project documentation, publishing configuration, and release evidence,
never from branch names or globally newest tags alone. The runner shall collect
paginated release/tag catalogs and the current target commit, bind the chosen
release name/commit to a complete catalog and available related Git objects,
and refresh this evidence before final output. Changed release evidence or target
revision shall force full review rather than reuse an unchanged assessment.
When policy, publication, or comparison cannot be established reliably, the
review shall continue with an explicit reason and target-branch fallback; the
release estimate shall be null, and the MR's target-relative assessment shall
select its label. Reports shall show the mode, named comparison basis, policy,
and separate rationales, keeping exact commits in private JSON. Existing plans
remain readable but cannot serve as contract-6 incremental baselines.
Every actionable finding, thread
correction, and author local fix shall contain either one exact-position
single-line or bounded multi-line suggestion or one content-addressed textual
unified patch validated against the exact reviewed head without changing the
checkout; a thread without a code correction shall explicitly use
`not_required`, and every open thread shall use an explicit reply, closure, or
author local-fix outcome rather than `no_publication`. It shall prepare direct
manual one-action publication-helper commands and local `git apply` commands with
explicit body files. Each remote action shall bind the current finalized plan,
exact payload, body digest, user, MR identity and refs, conversation, labels, and
a 24-hour expiry. The separately invoked helper shall serialize publication,
revalidate before writing, persist an in-progress reservation, and require a fresh
GitLab postcondition before recording success. Thread state shall depend on the
successful explanation receipt. Known successful effects from the same evidence
snapshot may satisfy freshness checks; unrelated conversation or label changes
shall require regeneration. Successful action replay shall not write again.
Only a proven process-start failure shall clear a reservation without a remote
postcondition. Ambiguous outcomes shall block further writes; explicit inspection
may resolve them through bounded read-only GitLab observations. The helper shall
retain a bounded redacted cause and exact recovery commands. It may retry an
unobserved effect only after the user explicitly selects the retry mode or accepts
its interactive duplicate-write warning; retry shall revalidate freshness and
shall never be automatic.
Old direct-command plans shall remain readable history and require regeneration
for guarded publication. Local patches retain advisory markers and exact-head
checks; markers shall not count as publication evidence. Preparation shall never
invoke publication or patch commands. Every invocation shall read every
open and resolved non-system discussion and all replies, including an unchanged
incremental scope. A thread closed by any user shall receive a concise reply only
when it adds information after checking the full conversation and current code.
Published Git patches shall use one
copy-ready quoted `git apply` heredoc. A thread-state command shall follow as a
separate action after its explanatory reply, and no state change shall be
prepared without one. Contract-5 plans shall bind every thread decision to the
full discussion chronology, including system notes; reject stale chronology;
retain explicit `unchanged` mode; require a validated `suggestion` or patch and
an open/reopened thread for an accepted problem; and require resolution for an
open thread found fixed, false-positive, duplicate, or not related. Its optional
`fixing_commit` shall contain only a natural title and immutable GitLab revision
URL when canonical evidence proves attribution. For remote
review, the runner shall own a resumable fail-closed state machine from prepared
evidence through a recorded independent critic when the selected mode requires
one, fresh finalize report, bound decision, contract-6 plan, baseline, Markdown,
and final chat rendering. It shall generate model-ready critic, decision, and content
templates with exact artifact, label, thread, latest-note, pipeline, complete job
inventory, and bounded failed/canceled trace bindings;
reject out-of-order, incomplete, stale, or structurally duplicate accepted findings and plans; keep reviewer finding details
out of chat; treat low findings as non-blocking; recursively collect bounded
child/downstream CI evidence; require trace-supported classification for every
failed/canceled job; permit `ready` only for complete CI evidence whose failures
are all proven manual process gates; and otherwise render blocking CI without
another blocking finding as owner decision required.
For a resolved thread with a sufficient existing explanation or applied GitLab
suggestion, it shall prepare no duplicate reply; a new reply is permitted only
when it adds a confirmed correction or independent information. Publication
prose shall apply `humanize`, avoid semicolons outside exact code, commands, and
quotations, and never claim to close a thread that is already resolved.
The plan shall display its producer release version stamped from the portable
release manifest during build, without a maintained version literal or runtime
checkout dependency. Metadata shall be compact, label changes and their command
shall appear once beside it, and actions shall have human-readable captions.
Local fixes shall retain copy-ready patch previews. Semantically equivalent
labels shall prefer namespaced labels based on their names and descriptions,
replacing existing plain equivalents without hardcoded alias matching.

For local WIP, `prepare-local --incremental auto` shall select `full`,
`incremental`, or `unchanged` using a compatible finalized `local_review_report`.
Compatibility requires complete evidence and unchanged checkout, HEAD, base, and
comparison ref. A changed boundary, missing or invalid baseline, or explicit
`--incremental off` shall select full review with a reason. An independent or
repeated review request alone shall not discard the baseline. Legacy snapshots
remain finalizable but do not establish a review baseline.
`finalize-local --report` shall bind the report to a fresh immutable snapshot,
validate cumulative finding IDs and dispositions, and atomically replace a
private pointer only after successful validation. Failed or stale finalization
shall preserve the previous baseline. A finalized report may be not ready.

The local report shall retain the agreed goal, acceptance criteria, constraints,
accepted risks, deferred work, decision evidence, checks, and findings. Each
finding shall distinguish severity from blocking status and record the violated
requirement, reachable scenario, evidence, consequence, change origin, minimum
remedy, and rationale. Closed or non-blocking dispositions shall not become
blocking without an explicit explanation and changed facts or user decision.
New requirements and pre-existing debt shall not block without explicit scope
approval. Required unrun checks shall block completion, and failed required
checks or open blocking findings shall prevent readiness regardless of severity.
Unchanged evidence shall not trigger another broad audit automatically.

For either target, the reviewer shall assess necessity and proportionality before
promoting candidates, preserve agreed limitations, give independent reviewers
the task decisions, and separate optional hardening from required corrections.
Reproduction alone shall not establish practical reachability or priority.
Repeated edge-case patches shall prompt consideration of a simpler supported
behavior, not automatic expansion. Structural fields shall not be presented as
proof of semantic judgment. Completion shall be based on agreed acceptance,
closed required findings, affected regressions, and named limitations, without
an automatic final broad audit, fixed round limit, or severity-only cutoff.

## Example

`code-review` maps a `major` SemVer assessment to the unique available
`semver::major`-equivalent label and prepares one manual label command; it
rejects an incomplete catalog before plan creation.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
