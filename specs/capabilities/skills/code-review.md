# `code-review`

## Purpose

Review local WIP or one exact GitLab MR for concrete defects and contract regressions.

## Triggers and Near-Misses

Trigger for review; near-miss: preparing an MR description or publishing a release.
Release verdicts belong to `release-review` unless both reviews are requested.

## Inputs and Outputs

Input is one exact MR URL or current local WIP. The external `reviewmatic` runtime
produces immutable evidence and decisions, a compact role-aware assessment, and
`runbook.md`. The portable archive contains authored instructions and materialized
references, not an embedded executable. Reviewer findings remain out of chat.
The runbook contains findings, compact previous-finding dispositions, metadata,
label delta, SemVer, validated fixes, body previews, and direct manual commands.
Detailed history and exhaustive label decisions remain in private JSON.

## Workflow Stages

Collect evidence/context, inspect exact-commit snapshots and affected consumers,
run independent critics when required, complete one draft, validate locally, and
finalize atomically. Resume retains the draft. Refresh retains candidates and
decisions while exposing changed analysis scope. Targeted repair creates a new
version without rerunning unrelated review. Publication is a separate user action.

## Dependencies

Git, relevant tests, authenticated `glab`, exact GitLab evidence, and host-native
independent subagents. Optional specialist profiles are not prerequisites.

## Remote/Local Effects

Preparation writes private artifacts but never edits the reviewed checkout or
publishes. Users can copy commands from `runbook.md` or launch `reviewmatic plan`.
The TUI executes the same `glab` operations without a shell. Local application uses
a separate worktree with separate commit and push confirmations.

## Errors, Partial, Escalation

Missing or incomplete evidence, unavailable required traces or critics, and
invalid bindings block review completion. Failed/canceled jobs require exact-head
trace-supported classification, including child/downstream pipelines. Only proven
manual process gates can be non-blocking. Trace collection bounds bytes, retains
an explicit truncated tail, and cleans up its process group under deadlines.
Schema diagnostics identify invalid fields; an invalid SemVer object is not
evidence that the publication baseline is absent. Insufficient targeted checks
stop repair, preserving the prior plan and unfinished draft.

## Unique Constraints

Role derives from authenticated user and MR author, never inference. Publication
prose continues the complete conversation naturally in the chosen language.
Private artifacts have bounded paths and permissions. Exact refs remain out of
chat and prose, but executable GitLab position arguments retain exact revisions.
Ordinary local edits need no user confirmation; external mutations remain manual.

## Requirement

### REQ-F-105 - Review exact changes

The workflow shall accept one exact MR URL or current local WIP and reject inferred
or multi-target remote input before collection. Remote collection shall retain
complete paginated discussions, notes, labels, commits, changes, exact Git objects,
release/tag catalogs, target revision, and exact-head CI evidence. Missing, binary,
non-regular, and over-budget inspection inputs shall be explicit.

`start-review`, `check-review`, and `finish-review` shall operate on one editable
draft. Local validation shall not recollect GitLab or freeze decisions. Runtime
timings shall distinguish collection, validation, and finalization from model
time. Successful finalization shall atomically replace the plan, runbook, and
baseline; failure shall preserve the previous result. New contract-7 guided plans
shall retain their exact review source for repairs. Older contracts shall remain
historically readable but shall not be repaired, migrated, or have guarded actions
executed by the new runtime.

Normal, deep, and changed incremental review shall require real independent
receipts. Available selected specialists are preferred; absent profiles fall back
to ordinary native subagents. Every selected contributor and finding shall be
retained with real run/session identities. Primary and critic candidates require
explicit dispositions; duplicate accepted findings are invalid. Fast review
without a critic requires justified low risk. Unchanged review audits discussions
without a critic. Required independence is not waived for unavailable delegation.

Incremental analysis shall follow changed code, conversations, metadata, and CI,
including affected unchanged consumers. Previous accepted findings and recommended
issues retain stable IDs and explicit current dispositions; rejected candidates
are reconsidered only when dependencies change. Changed comparison boundaries,
rewritten history, incompatible or incomplete state select a full review.
`refresh-review` shall preserve findings and dispositions rather than start an
empty draft. Original critic receipts remain historical, never rebound to new
digests. CI-only refresh shall retain code analysis and receipts, attach an
immutable supplemental snapshot, and request only updated CI assessments and
affected prose. The verdict and report shall reflect the used CI snapshot.
MR `pipeline`, `head_pipeline` and latest-build timestamps are CI-derived fields;
their changes alone shall not invalidate code analysis. Head, metadata,
discussion and conflict changes remain material freshness inputs.

Every invocation shall read complete open/resolved conversations. Resolution,
approval, green CI, and a short "Fixed" are not proof. Thread decisions bind full
chronology, including system notes. Accepted problems require a validated fix and
open/reopened state; fixed, false-positive, duplicate, or unrelated open threads
prepare closure. Neutral/questions do not change state. Resolved threads with a
sufficient explanation or applied suggestion prepare no redundant reply.
Fixing-commit attribution requires an immutable link supported by evidence.

The reviewer shall establish necessity, reachability, consequence, change origin,
and proportionate minimum remedy. Severity does not alone determine scope or
local completion. Non-low remote findings block readiness; low findings do not.
Accepted risks and deferred requirements are not reopened without changed facts
or an explicit decision. Completion checks agreed requirements and affected
regressions, not all hypothetical defects or an automatic final broad audit.

Suggestions shall be the default. One finding may own multiple positioned
`suggestions` records, with `split_rationale` for safe partial application. Each
part and the combined result shall be checked against the exact head; overlapping
ranges are invalid. Visible context positions are supported. Partial application
shall not be claimed as a complete correction. Patch fallback requires a concrete
`patch_reason` for technical impossibility or unsafe division. Input body prose
shall exclude the diff and apply command; the renderer adds one portable quoted
heredoc with fences safe for embedded Markdown. Temporary-index patch validation
rejects binary, symlink, submodule, rename, traversal, and oversized inputs without
editing the checkout. Author local fixes remain patches.

`repair-review` shall support only new guided plans. Presentation repair includes
unchanged-meaning wording, layout, command/position correction, and equivalent fix
representation; equivalence includes the complete resulting tree and file modes.
The agent compares meaning and records rationale/checks, not a purported machine
proof of semantics. A different fix of a confirmed problem requires targeted
consumer/failure-path checks, not automatically a new critic. Changed findings,
assessments, requirements, or verdict require a new targeted independent critic.
Uncertain meaning requires decision repair. Missing checks stop repair without
automatically broadening review. Publication history does not gate local repair.

The runbook shall omit empty sections and duplicated findings, patches, and
commands. Previous findings receive one compact row with a short name, localized
result, and next action; detail and commands stay together, not under unrelated
sections. Metadata and label delta stay compact; exhaustive applicability,
unresolved labels, and removal reasons stay private. SemVer distinguishes MR
contribution from accumulated release impact, selects compatibility labels from
the MR contribution, establishes policy from project evidence, and reports a
reasoned target fallback without a fabricated release estimate. Equivalent labels
prefer namespaced catalog entries without hardcoded alias names.

Manual publication shall have no persistent locks, reservations, receipts, TTL,
automatic freshness reads, polling, or automatic retries. One send performs one
operation and exposes its exit code and bounded redacted diagnostics. Replies and
state changes are independently runnable; the TUI also offers their explicitly
chosen sequence. The user verifies GitLab in a browser and chooses repetition.
Timeouts and cancellation may leave accepted remote requests and repetitions may
duplicate them; this risk is visible but does not create a persisted block.

The TUI is experimental and outside blocking behavioral acceptance; see
[REQ-F-548](../../requirements/functional/README.md#req-f-548---verify-gitlab-workflows-against-a-persistent-local-ce-server)
for the acceptance boundary. Preparing a runbook still requires the reviewmatic
backend; its finished direct `glab` commands execute without reviewmatic.
Opening/reading/navigating the TUI shall require no network. During sends, reading,
navigation, exit, and cancellation remain available. The UI shows readable text,
separate reply/context views, concrete errors rather than truncated JSON, and
explicit action choices. Opening a detail never publishes. Human body edits save
the plan/runbook without sending and preserve validated code. TUI statuses describe
local command execution, never remotely verified publication.

Local WIP uses its own immutable snapshots and cumulative report, not GitLab
publication state. `prepare-local --incremental auto` selects full/incremental/
unchanged from compatible complete checkout/HEAD/base/ref evidence. Legacy or
changed boundaries select full review. `finalize-local --report` checks freshness
and continuity before replacing its private pointer. Reports retain goal,
acceptance, constraints, decisions, risks, deferred work, checks, and severity
separate from blocking status. Required unrun/failed checks block completion.

#### Verification

Runtime and fixture tests cover local validation, real critic identity contracts,
atomic rollback, cumulative findings, targeted repair, refresh without lost
findings, original receipt preservation, CI-only refresh, grouped suggestions,
Markdown fences, field diagnostics, direct writes without GETs or publication
state, errors, repetition and cancellation. TUI behavioral, Ink and PTY suites
remain separate experimental sources and are not run by the default gate.
Backend worktree checks remain mandatory. Tests use synthetic GitLab responses,
never live publication.
Structural tests do not prove the model's semantic judgment.

Transport tests use real `glab` 1.120.0 with isolated configuration and a local
HTTP server. Positioned commands send one nested JSON `position` object with
numeric line fields; bracket field names are unsupported. These tests prove CLI
serialization, not acceptance by a remote GitLab instance. Missing `glab` fails
the required test rather than silently skipping it.

Exact duplicate check strings render once without discarding distinct evidence.
Grouped suggestion parts with explanatory prose are complete publication bodies;
bare blocks inherit shared prose for compatibility. The agent preserves necessary
caveats in each complete part. Presentation repair regenerates contract-7 commands
locally while preserving findings and original critic receipts. User-facing launch
commands remain `reviewmatic plan`, without a `mise exec` wrapper.

## Example

An MR contribution assessed as patch selects its unique catalog compatibility
label and prepares a direct manual label command. A wording correction later
updates `runbook.md` without launching another code review.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
