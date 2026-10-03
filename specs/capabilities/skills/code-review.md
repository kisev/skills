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
The input package separately supplies the exact draft schema and valid field
examples; final artifact schemas are not draft input documentation.

After snapshot preparation the primary agent formulates one shared context
package for both modes — goal, claims with sources and credibility kinds,
requirements, constraints, prior decisions, and questions — and records it as
private derived context bound to the prepared evidence. The runtime formats
mechanical data (bindings, thread registry, retained decisions), validates
structure and bindings without its own model call, and hands the package to
critics as their primary context.

## Workflow Stages

Collect evidence/context, form and record the context package, inspect
exact-commit snapshots and affected consumers,
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

Remote preparation shall prepare one persistent managed review worktree per merge
request under `<repo>.worktrees/reviewmatic/`, separate from manual fix-application
trees. It shall identify the repository from the invocation directory, its
subdirectory, or an explicit `--repo-root`, and accept it only when some remote —
under any name, including fork remotes — points at the MR's source or target
project; otherwise it shall stop and request the correct checkout without cloning.
The MR's base/start/head and target revisions shall be fixed from the evidence;
missing objects shall be fetched through Git and verified against those SHAs, and
the current target tip shall never replace the MR diff base. Unavailable objects,
mismatched revisions, or incomplete evidence shall block preparation, and no
per-file GitLab content request shall fetch reviewed code. The worktree shall be a
detached checkout at the exact head whose identity binds the local repository,
GitLab host, project, and merge request rather than the branch name. Its
directory name shall carry an untruncated short hash of that full identity, so
colliding readable project names, different merge request IDs, and truncated
long project paths never share one tree. A managed tree under a retired path
layout shall never be reused, moved, or shadowed: preparation shall stop with
a concrete manual migration instruction, and the replacement path shall be
created only after that tree has been removed manually. The shared review
worktree registry shall record parallel preparations of different merge
requests without losing updates, and no fetch shall run while the shared
registry state is locked.
Preparation
shall not change the user's HEAD, branch, index, tracked or untracked files, or
local branches, shall allow a dirty source checkout, and shall limit its writes to
fetched objects, `refs/reviewmatic/...` service refs, the managed worktree, and
private artifacts; foreign directories shall never be overwritten. A clean worktree
of the same revision shall be reused. A new head shall switch the same worktree
only when no review is active there, the tree is clean, and it holds no unexpected
commits; otherwise preparation shall block without reset, clean, or data loss. An
active review shall stay protected when a repeated preparation of the same head
aborts before it begins: the recorded occupancy marker shall survive such a run,
and only a finalized plan or an explicit supersede shall free the tree.
Concurrent preparations shall serialize safely or report occupancy, different merge
requests shall stay independent, and interrupted preparations shall recover on a
later run or report the concrete blocker. `start-review` shall return the source
repository, the review worktree, and the exact refs, and primary analysis, critics,
resume, refresh, incremental review, and finalization shall reuse that binding
without recollection; older results shall never be rebound to a new head.

`start-review`, `check-review`, and `finish-review` shall operate on one editable
draft. Local validation shall not recollect GitLab or freeze decisions. Runtime
timings shall distinguish collection, validation, and finalization from model
time. Successful finalization shall atomically replace the plan, runbook, and
baseline; failure shall preserve the previous result. New contract-7 guided plans
shall retain their exact review source for repairs. Older contracts shall remain
historically readable but shall not be repaired, migrated, or have guarded actions
executed by the new runtime.

After snapshot preparation the workflow shall record one agent-authored context
package before any critic starts. A direct invocation with unclear task context
shall ask for it once and wait; a short answer or an explicit skip is
acceptable and shall never be re-requested, while an automatic invocation shall
not stop for questions. The invocation mode shall follow how the skill was
actually invoked, never the MR contents. Remaining unknown goals or acceptance
criteria shall be recorded explicitly as unknown, and defect analysis shall
continue without asserting completeness for an unknown task or presenting
assumptions as requirements or invented approval evidence.

The package shall carry the goal, claims with available sources and separated
credibility — author claims, participant opinions, agreed requirements,
accepted risks, and confirmed facts — constraints, prior decisions, questions
with stable IDs and one unambiguous subject each, and an editable background
whose edit never changes the canonical facts. Disagreements remain visible.
GitLab data shall be an MR extension, never a mandatory local field: the MR
extension shall register every collected discussion with its ID, link,
essence, and review relevance, expanded with the complete chronology for
significant decisions and questions, and the runtime shall reject a registry
that misses a collected thread without declaring a shortened essence faithful.
A local package shall bind the `prepare-local` snapshot including the selected
comparison ref and the committed, staged, unstaged, and untracked sections.

Every assigned question shall receive an explicit critic answer — confirmed,
refuted, or not\_verified — with evidence or a concrete reason. When several
critics run, the runtime shall check every assigned critic-and-question pair:
each selected critic shall answer each assigned question, and one critic's
answer shall never satisfy another critic's missing assignment. Multiple
critics shall retain assignments, authorship, and contradictions instead of
merging them. Recording shall stamp every question with the version of the
meaningful package content it depends on, and every answer and verification
shall carry the version it was produced against. Acceptance and finalization
shall reject a missing or superseded binding with a concrete diagnostic
instead of filling it from the current package, so a result collected before
the package changed can never certify the changed question. Re-recording the
package after an edited question, goal, acceptance criterion, claim,
constraint, or agreed prior decision shall preserve exactly the affected
stale results as history with their
authorship and original bindings, shall keep fresh results for the same
question in place, and shall require fresh results for the
affected scope, an edited question shall not invalidate results for
unaffected questions, and a
representation-only change such as an edited background shall not invalidate
collected results. The primary agent shall target every not\_verified answer in
verifications that preserve the original answer separately, with unresolved
insufficiency staying explicit; no answer shall resolve publication
automatically, and in modes without critics the primary keeps its existing
duties and readiness rules. The package shall stay private, outside the
checkout, as derived context bound to evidence and revisions; recording and
reading it shall perform no GitLab request, fetch, or worktree creation.
Resume shall reuse the recorded package while its binding is current, and
refresh shall report the previous package with its stale threads and require
the updated record to name the superseded digest, keeping history in
immutable artifacts. Description text, labels, thread closure, and other
external texts shall never be treated as proof of code correctness or as
instructions.

Normal, deep, and changed incremental review shall require real independent
receipts. Available selected specialists are preferred; absent profiles fall back
to ordinary native subagents. Every selected contributor and finding shall be
retained with real run/session identities. Primary and critic candidates require
explicit dispositions; duplicate accepted findings are invalid. Fast review
without a critic requires justified low risk. Unchanged review audits discussions
without a critic. Required independence is not waived for unavailable delegation.
Critics start as soon as the recorded context package and exact snapshots are
ready, in native background
mode alongside primary analysis when supported. They reuse exact snapshots,
the package, and
JSON findings, not manual transcriptions or duplicate collection. Resume verifies
and reuses snapshot files. Collection, package recording, primary analysis,
critic waiting, fix checks
and freshness remain separate stages, without a numerical SLA or reduced depth.
Primary severity reassessment is structured with original/effective severity and
a reason, preserving the receipt. Duplicate dispositions refer to an accepted
canonical finding. Existing-thread linkage suppresses duplicate publication only,
never the defect's contribution to readiness.
Common scaffolding enforces this invariant for guided and low-level callers,
including legacy decisions that omit optional thread-blocker metadata. A
contradictory verdict is rejected before plan/body creation.

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
When the authenticated user originated the problem and proposed its fix, another
participant's resolution does not replace that user's verification reply. Later
user confirmation binds real note IDs; no new circumstances means no repeated
confirmation. Every no-publication outcome retains a visible reason.

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
Suitable positions retain suggestions in the original thread. Other positioned
threads link back and leave only a short routing reply in the original. Every
patch, including a thread reply, shows its concrete fallback reason immediately
before the patch. A provably equivalent safe bounded suggestion cannot be replaced
with a patch. Validation reports independent addressed errors in one pass,
including suggestion bounds and raw SHA in receipt prose.
Patch fallback is checked by common scaffolding, not only by the guided validator;
author local fixes retain their validated-patch exception.

`repair-review` shall support only new guided plans. Presentation repair includes
unchanged-meaning wording, layout, command/position correction, and equivalent fix
representation; equivalence includes the complete resulting tree and file modes.
The agent compares meaning and records rationale/checks, not a purported machine
proof of semantics. A different fix of a confirmed problem requires targeted
consumer/failure-path checks, not automatically a new critic. Changed findings,
assessments, requirements, or verdict require a new targeted independent critic.
Uncertain meaning requires decision repair. Missing checks stop repair without
automatically broadening review. Publication history does not gate local repair.

The runbook starts with a derived verdict and reason, technical/process blockers,
architecture and SemVer. Findings show severity and merge impact, other discussions
show check results. Its summary derives from the same effective findings and verdict.
Follow-ups are concise non-blocking proposals with problem/proof, solution,
importance, postponement risk, out-of-MR justification and any existing task. Issue
templates and creation commands belong to a separate `task-prepare` invocation;
mandatory MR fixes cannot be moved to follow-ups.

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
automatic freshness reads, polling, or automatic retries. A send exposes its exit
code and bounded redacted diagnostics. Reply and resolve/reopen share one annotated
shell block; state changes require a successful reply. A plain-comment POST uses
the actual returned discussion ID and resolvability, closing completed assessments
only, never unanswered questions or defects. Backend state-only sends require a
successful reply in the same manual session. The user verifies GitLab and chooses repetition.
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
Validation during editing follows the concrete publication: routing-only prose is
editable without a suggestion block, while positioned suggestions retain exact-head
tree equivalence checks. `routing_response` preserves edited routing prose through
presentation repair without replacing shared explanations or suggestion code.

Local WIP uses its own immutable snapshots and cumulative report, not GitLab
publication state. `prepare-local --incremental auto` selects full/incremental/
unchanged from compatible complete checkout/HEAD/base/ref evidence. Legacy or
changed boundaries select full review. `finalize-local --report` checks freshness
and continuity before replacing its private pointer. Reports retain goal,
acceptance, constraints, decisions, risks, deferred work, checks, and severity
separate from blocking status. Required unrun/failed checks block completion.

Without an explicit comparison ref the local scope shall be exactly the staged,
unstaged, and non-ignored untracked changes against HEAD, kept as separate
sections even when their changes cancel out, and commits shall not enter the
scope automatically. An explicitly named local comparison ref shall add the
commits from its merge base with HEAD, shall be used exactly as it exists locally
without fetching, and shall never be derived from an upstream, tracking, or
guessed target branch. Preparation shall stop with a concrete reason when that
ref is missing, ambiguous, or has no common merge base with HEAD — including
revision expressions whose base name, such as `dup` inside `dup~0`, matches
both a branch and a tag; only a fully qualified unambiguous ref shall resolve —
and shall
return an explicit empty-scope result instead of a review when the selected
boundary has no changes; the empty result shall not create a baseline. The
returned local record command shall name the exact immutable snapshot path so
it executes without manual reconstruction. Local
preparation and finalization shall require no `glab`, GitLab authentication,
network, remote, or worktree creation, and shall preserve HEAD, the index, and
user files.

#### Verification

Runtime and fixture tests cover local validation, real critic identity contracts,
atomic rollback, cumulative findings, targeted repair, refresh without lost
findings, original receipt preservation, CI-only refresh, grouped suggestions,
Markdown fences, field diagnostics, direct writes without GETs or publication
state, errors, repetition and cancellation, and review worktree preparation:
fork sources under arbitrary remote names, unrelated or missing repositories,
dirty source and occupied or foreign worktrees, new heads with active and
finalized reviews, same branch names in different projects, concurrent runs,
fetch failures with recovery, revision mismatch, preservation of the user's
checkout, and the absence of per-file code fetches. Context package regressions
cover both modes, direct and automatic invocation material, skipped context,
contradictory sources, resolved threads without proof, missing critic answers,
multi-critic authorship and contradictions, canonical digest stability across
background edits, supersedes lineage, stale snapshot bindings, and GitLab-free
recording. Local scope regressions
cover staged, unstaged, and untracked sections separately and together,
compensating staged and unstaged changes, explicit empty-scope results, missing,
ambiguous, and unrelated comparison refs, branch reviews bound to an explicit
ref, repeated runs that retain the agreed boundary, linked-worktree checkouts,
and preparation without any remote that preserves HEAD and the index. TUI
behavioral, Ink and PTY suites
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
