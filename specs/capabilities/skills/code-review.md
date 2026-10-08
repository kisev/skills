# `code-review`

## Purpose

Review local WIP or one exact GitLab MR for concrete defects and contract regressions.

## Triggers and Near-Misses

Trigger for review; near-miss: preparing an MR description or publishing a release.
Release verdicts belong to `release-review` unless both reviews are requested.

## Inputs and Outputs

Input is one exact MR URL or current local WIP. The Python `reviewmatic` runtime
produces immutable evidence and decisions, a compact role-aware assessment, and
`runbook.md`. The portable archive contains authored instructions and materialized
references, not an embedded executable. Reviewer findings remain out of chat.
The runbook contains current findings and proposals, metadata,
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

Python 3.12+, `uvx`, Git, relevant tests, authenticated `glab`, exact GitLab
evidence, and host-native independent subagents. Optional specialist profiles
are not prerequisites. The runtime is invoked from a selected Git ref as
specified by [REQ-I-428](../../requirements/interfaces/README.md#req-i-428---run-reviewmatic-from-a-selected-git-ref).

## Remote/Local Effects

Preparation writes private artifacts but never edits the reviewed checkout or
publishes. Users copy commands from `runbook.md`; no in-application send
interface exists. Local application uses a separate worktree with separate
commit and push confirmations.

## Errors, Partial, Escalation

Missing or incomplete evidence, unavailable required traces or critics, and
invalid bindings block review completion. Failed/canceled jobs require exact-head
trace-supported classification, including child/downstream pipelines. A bridge
job has no trace endpoint: bridges stay in the job inventory without a trace
fetch, their failure is classified through the collected downstream pipeline,
and a missing bridge trace never marks the evidence incomplete. The
one-process run bounds every stage — a stage repeating without progress more
than three times stops loudly with the collected evidence errors and preserves
the state for resume. The runtime identifies itself: `runtime-info` prints the
package version and the resolved installation commit (the nested PEP 610
`vcs_info.commit_id` uv writes, legacy flat fields, a URL-pinned SHA, or an
honest `unknown` for non-git installs), and the agent pins the moving channel
to an exact SHA before starting and verifies the pin with that single call. A
resumed `--participants` answer replaces the recorded panel only while no
critic receipt is bound; with bound receipts it is refused loudly with the
bound names and the honest path. The panel poll renders after the mode and
background resolve: only a background above the OCR CLI limit excludes the
OCR engine with the reason. Incremental review retains the delta-scoped engine. The same offline render
measures the size the critic would run, the CLI invocation prefights the
limit before spawning, and the verbatim locale-keyed poll text plus its fixed
glossary are presented word for word. Tail refusals name the rule, the
offending path, and the accepted form — the canonical decision and critic
validators and the plan, thread, suggestion, and patch checks each answer with
one such record. Only proven
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
request under the resolved repository's `.worktrees/reviewmatic/`, separate from
manual fix-application trees. It shall resolve the repository from an explicit
`--repo-root` when that checkout has a matching remote and can provide the exact
objects, and otherwise from one managed clone per host and project under the XDG
cache, shared across the project's merge requests with an incremental fetch; the
invocation directory shall not select the repository. A provided checkout whose
objects cannot be fetched shall fall back to the managed clone instead of
failing. The MR's base/start/head and target revisions shall be fixed from the
evidence; missing objects shall be fetched through Git and verified against those
SHAs, and the current target tip shall never replace the MR diff base. The local
merge base shall be verified against the evidence base SHA, and the real
merge-base delta size — local file, insertion, deletion, and binary-file counts
measured from that verified merge base — shall be recorded in the review context
so size decisions use it instead of server counts. Unavailable objects,
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

Normal and changed incremental review shall run as an orchestrated
panel and shall require real independent receipts plus one arbitration
receipt. Review depth shall be selected through the recorded panel composition —
more independent critics mean a deeper review — and there is no separate depth
mode. The host agent records the panel once — the critic count and
composition and the arbitrator — through `record-participants`; a recorded
composition is fixed once receipts exist, and the recorded profile, provider,
and model configuration shall never be substituted silently. Each selected
critic runs as an independent parallel reviewer over the same recorded package
and exact snapshots without seeing other critics' output, without recollecting
GitLab, and without rebuilding the prepared file map; each receipt is imported
verbatim with `record-critic --participant <name>` and bound to its selected
participant. A critic entry may declare `engine: "ocr"` to select the
OpenCodeReview CLI instead of a model subagent, optionally with the
`--ocr-provider` and `--ocr-model` overrides recorded at selection time
(without them the OCR CLI uses its own provider configuration); panels may mix
OCR and model critics freely. For an OCR critic the runtime shall return a
ready `record-ocr-critic` command that renders the recorded package as a
Markdown background file, invokes the OCR CLI with `--format json` over the
exact reviewed range under a bounded timeout, maps the comments into one
receipt carrying the OCR run identity and engine metadata, and binds it to the
participant through the standard import path; an OCR receipt carries findings
only, never answers critic-assigned questions, and in incremental reviews runs
scoped to the `from_head..head` delta: the receipt binds the incremental delta
digest and `target_finding_ids` names exactly the previously reported findings
rendered into its background (those whose previous publication position or
patch intersects the changed paths, as consultation coverage without mandatory
historical dispositions), so with no model critic selected the arbitrator resolves every
assigned question through `question_verifications`. When every selected receipt is imported, the runtime shall
return the ready arbitrator task with a complete arbitration input — the
package binding, every critic receipt verbatim, and the reported
contradictions. The arbitrator is a separate selected subagent that confirms
or refutes every critic finding with a concrete reason, resolves every
contradiction and `not_verified` answer through targeted evidence checks,
merges duplicates without losing authors or opinion differences, and records
the consolidated decisions in one `code-review/arbitration/v1` receipt
imported verbatim with `record-arbitration`. The receipt shall select exactly
one merge verdict — `decline`, `push_back`, `merge_then_fix`, or `merge` —
with an evidence-based rationale; the runtime shall reject a receipt without
that verdict and render it in the plan, runbook, summary, and chat. Findings
discipline belongs to the arbitrator: only a finding that moves the merge
verdict or the readiness verdict, or joins the action list, enters the runbook
findings; every other candidate stays a ledger entry with its reason, and the
critics never see this filter. Every critic finding shall trace its symptom to
the changed lines, and an unreachable-code claim requires proving
unreachability from a real entrypoint. The runtime shall reject a
receipt that leaves any candidate finding, merged finding, or contradiction
without a verdict, shall never rewrite arbitrator text, and in panel mode
shall restrict `record-input` to the orchestrator's identity fields. The host
agent adds no full review pass of its own. The one-process `run` path drives
the same panel: the poll is the decision point, answered through
`run --participants` with the same selection schema and the optional
`--ocr-provider`/`--ocr-model` overrides; without the answer the run stops
once and prints the selection template with the exact resume command. The run
executes OCR critics mechanically inside the process without an authoring
stop, stops once per model critic with that participant's ready receipt
template and the exact `record-run-critic` import command, and merges the
complete panel into one aggregate critic receipt through the contributors
convention. An invalid selection is a loud refusal that records nothing, a
selection without a panel stage (a fast or unchanged review) is refused, and
the run results name the panel with every critic's engine and receipt
identity. Context collection treats degraded discussions as a loud refusal:
an unusable discussion entry or a note with an empty or missing body stops
the review with an addressed error instead of writing a silently empty
artifact. Preparation shall expose already
collected evidence through prepared
runtime representations: `start-review` and `resume-review` shall return a
readable scope overview built from recorded evidence — target identity, the MR
description and other author-provided text flagged as claims, changed paths,
discussion threads, pipelines with completeness and truncation markers, the
best-effort file-relation map with its incompleteness notice, and
every exact snapshot, inspection, and managed-worktree path — plus a compact
input contract naming exactly the editable fields for the current stage;
`scope-review` shall re-print that overview from recorded artifacts without any
GitLab request. Standard input shall not require reading the full artifact
schema, guessing envelope shapes, computing digests, or globbing for files.
Recording the context package shall return one ready critic task per selected
participant with the
recorded package path, question context versions, exact snapshot paths, the
receipt template, and the exact import command. The runtime shall provide
mechanical assembly operations — `record-input` for semantic sections of the
MR draft and the local report, `record-critic` for one independent receipt —
that apply the agent's decisions by upserting list entries by identity while
preserving machine fields, bindings, receipts, and digests, that never
substitute a semantic verdict by default, and that keep critic findings,
dispositions, and targeted verifications separate: importing a receipt shall
preserve its findings, answers, authorship, and per-answer context versions
verbatim, shall reject an answer bound to another package version with the
question's expected version instead of rebinding it, and shall never create
dispositions for critic findings. An existing thread decision shall be updated
through its id plus the semantic fields; the runtime shall keep the prepared
url, state, and note bindings, reject a sent machine field that disagrees with
the prepared value, and validate the merged record against the full input
schema, so no hand-copied digest or spread-assembled thread record is ever
required. Locally imported critic answers shall merge by full identity — the
question, the context version each answer was produced against, and the
authoring run and session — instead of replacing the stored list: a repeated
identical result is not duplicated, a different result under the same identity
is rejected while the original stays, primary verifications stay separate and
may be revised by the primary, and a preserved `not_verified` answer keeps
demanding a verification before a ready verdict. The local draft shall be
selected by the current snapshot: preparation materializes it, an existing
draft bound to the same evidence survives untouched, and a stale draft is
rebuilt from the current snapshot and finalized baseline with runtime-owned
fields updated and historical superseded results retained, so the documented
`prepare-local → record-package → record-input → finalize-local` order works
without re-recording the package or repairing bindings by hand. A repeated
`scope-review` shall restore the carried task, the recorded baseline, and the
exact draft and template paths from recorded state without mutating
preparation or collecting evidence again.
Validation and import failures shall name
the concrete field, the reason, and the allowed form — including canonical
schema failures — and a failed operation shall leave the previous stored
result unchanged instead of serving it as current. Malformed list shapes —
`null`, a non-array, or a `null` entry — shall be rejected with addressed
diagnostics before any list is iterated, never as a generic crash. The managed
review
worktrees shall be readable by the agent through a structural permission
preset; no per-repository path, shell, or edit permission shall be added for
them, and secret denies and explicit user denies keep priority.
Available selected specialists are preferred; absent profiles fall back
to ordinary native subagents running the host session's agent, provider, and
model. Every selected contributor and finding shall be
retained with real run/session identities. Every critic candidate and every
merged finding requires an explicit arbitrator verdict; duplicate accepted
findings are invalid, and a disagreement alone never hides a finding from the
runbook. Fast review
without a critic requires justified low risk. Unchanged review audits discussions
without a critic. Required independence is not waived for unavailable delegation.
Critics start as soon as the recorded context package and exact snapshots are
ready, in native background
mode alongside the panel launch when supported. They reuse exact snapshots,
the package, and
JSON findings, not manual transcriptions or duplicate collection. Resume verifies
and reuses snapshot files, reports the recorded participants, and never asks
for a recorded composition again. Collection, package recording, critic waiting,
arbitration, fix checks
and freshness remain separate stages, without a numerical SLA or reduced depth.
Primary severity reassessment is structured with original/effective severity and
a reason, preserving the receipt. Duplicate dispositions refer to an accepted
canonical finding. Existing-thread linkage suppresses duplicate publication only,
never the defect's contribution to readiness.
Common scaffolding enforces this invariant for guided and low-level callers,
including legacy decisions that omit optional thread-blocker metadata. A
contradictory verdict is rejected before plan/body creation. The orchestrator
shall pass the materialized simplification criteria reference into every critic
task and the arbitrator task; critics shall report complexity as ordinary
findings with complete fields, a pre-existing bloat candidate shall become a
recommended issue instead of a finding, and in local reviews it shall keep
`origin: pre_existing` and never block.

The shared renderer shall derive the accepted set from both primary and critic
findings with their recorded dispositions and effective severities. Accepted
findings rendered through `render-review` shall carry a publication intent in
the app-layer disposition or run's authoring-only publication intents. A line
fix shall use a semantic source target (`path`, exact `before` excerpt) and
replacement text; the runtime shall locate the target and derive the visible
anchor and bounded suggestion range, including multi-line replacements and
grouped semantic parts. Multiple matching excerpts shall request a concrete
clarification while preserving authored prose, never require manual range
or line authoring. An existing-thread intent shall bind exactly one prepared
thread named by the finding's dependencies. The generated prose surface shall
retain row identity handles and reject structural publication stamps and
SemVer bindings. Panel prose edits shall preserve arbitration decision keys
and retain the semantic-only thread representation in `arbitration.content`.
After rendering, direct `record-input` edits outside session identity shall
require a recorded repair kind.

The primary `run` tail shall invoke this renderer after recording the decision
and expose `content-prose-<digest>.json` applied through `record-prose`. Normal
completion shall not require structural `scaffold-review` input. Canonical
v2 decisions shall exclude authoring-only intent fields. Each new runbook shall
stand on the current snapshot without inherited IDs, historical revisions,
required proposal carryover, previous-finding assessments, or ledger coverage.
This replaces mandatory historical synchronization. Historical artifacts shall
remain immutable. Optional `incremental.history_context` shall expose previous
findings, reasons, decisions, proposals, and rejected candidates with snapshot
bindings to critics and arbitration. Unavailable or incompatible history shall
warn without blocking a complete current review. Follow-ups shall remain
proposals without an `update_issue` action.

Every generated prose row shall match its accepted input. Prepared `finding_id`
handles shall be returned unchanged, with unknown, duplicate, or substituted
identities refused. The runtime shall derive SemVer bases and bindings from
catalog and local Git proof. Policy-specific selection shall accept a collected
`{name,source}` handle and derive its SHA. Missing proof shall have an addressed
fallback, never a guessed basis. Labels shall retain exhaustive catalog coverage
as `{name,status,rationale}`. Recorded rejected-candidate decisions shall supply
their existing reasons and source bindings without repeated authorship.

Re-anchor shall preserve the original decision, panel receipts, and authored
prose as private history. New evidence shall receive a separate delta check
from a fresh independent native session of the selected verifier, covering the
changed paths, affected conclusions and dependencies, conversation and
metadata changes, and current CI. Source-location mapping shall establish only
a position, never factual confirmation. Each affected conclusion shall be
confirmed, refuted, revised, or explicitly not verified with evidence; unresolved
results shall block completion and request addressed work. Pipeline completion
without code change shall update CI assessment without requiring code analysis.
New conversations shall receive substantive checks. Confirmed authorship
shall carry automatically; refuted or changed conclusions shall revise only
their affected judgments and fixes. New delta findings shall need addressed
dispositions without restarting the complete review. Old receipt digests shall
never be rewritten: new current-bound receipts and decisions shall record the
separate delta verification with the original artifacts retained as provenance.
Validated rendered drafts shall checkpoint into this same run tail; unfinished
prose shall refuse checkpointing without discarding authorship. Rendering shall
scrub current and historical SHA tokens from the copied Markdown/chat
presentation and machine-copyable body files, including critic, CI, and SemVer text, retaining original private
evidence, immutable links, and executable fix code.

Incremental analysis shall follow changed code, conversations, metadata, and CI,
including affected unchanged consumers and OCR over the delta. Analysis scope
shall not imply runbook inheritance. A current problem shall remain reportable
even when history contains it under another ID. Changed comparison boundaries,
rewritten history, incompatible or incomplete state select a full review.
`refresh-review` shall preserve findings and dispositions rather than start an
empty draft; a panel plan keeps its selected participants without receipt
bindings and expects fresh critic receipts plus a fresh arbitration receipt
against the refreshed package. Original critic receipts remain historical, never
rebound to new digests. Finalization itself shall be local: `finish-review`
performs no GitLab request and no new analysis pass, keeps every fix check
against the exact reviewed snapshot, and leaves post-review drift to the
explicit `refresh-review` and to the head check guarding every manual
publication block. The verdict and report shall reflect the used CI snapshot.
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

Suggestions shall be the default. The materializable templates — the run
content template and the arbitrator receipt template — shall pre-render one
formally complete publication block per valid variant for every accepted or
candidate finding, with mechanical fields filled and judgment placeholders
structurally detectable: an unfilled variant shall refuse with fill-or-delete
guidance naming the missing judgment fields, never pass silently, and the
rule refusals shall name their rules (positions, the patch-prose split, the
single-block suggestion rule). One finding may own multiple positioned
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

`repair-review` shall support only new guided plans. Repair routes by cost:
publication or arbitration texts with unchanged decisions repair through a
fresh arbitration receipt from a new arbitrator session whose decision sections
are identical — the import is atomic, rewinds nothing, and a receipt that
changes a decision under this path is rejected; critic content checked before
arbitration replaces the aggregate receipt in the run path
(`replace-artifact --kind critic_receipt`) and takes `refresh-review` in the
draft path; post-plan texts take plan repair; changed evidence alone takes
`refresh-review`. Presentation repair includes
unchanged-meaning wording, layout, command/position correction, and equivalent fix
representation; equivalence includes the complete resulting tree and file modes.
The agent compares meaning and records rationale/checks, not a purported machine
proof of semantics. A different fix of a confirmed problem requires targeted
consumer/failure-path checks, not automatically a new critic. Changed findings,
assessments, requirements, or verdict require a new targeted independent critic,
and for a panel plan a fresh arbitration receipt from a new arbitrator session
while the recorded panel selection stays fixed.
Uncertain meaning requires decision repair. Missing checks stop repair without
automatically broadening review. Publication history does not gate local repair.

The runbook starts with a derived verdict and reason, the arbiter's merge
verdict with its rationale, technical/process blockers,
architecture and SemVer. Findings show severity and merge impact, other discussions
show check results. Its summary derives from the same effective findings and verdict.
A panel runbook adds a review-panel section naming each critic and the arbitrator
with the recorded profile, provider, and model — private to the runbook and never
part of published GitLab texts — and an arbitration-verdicts section that keeps
every candidate visible with its verdict and the arbitrator's reason, including
refuted and duplicate findings, and names who raised each finding and which
duplicates were merged into it without losing authors or opinion differences.
Follow-ups are concise non-blocking proposals with problem/proof, solution,
importance, postponement risk, out-of-MR justification and any existing task. Issue
templates and creation commands belong to a separate `task-prepare` invocation;
mandatory MR fixes cannot be moved to follow-ups.

The runbook shall omit empty sections and duplicated findings, patches, and
commands. Before finalization, `scrub-preview` shall run as a pure
computation — the draft's user-facing fields plus the same-builder dry-run
plan Markdown and chat — and list every raw-SHA exposure with its line,
token, and source, writing nothing and exiting nonzero while any remain; the
finalization refusal itself shall name the first exposure's line, token, and
evidence source plus the count and lines of the rest. Publication input
errors shall separate the allowed input keys from the runtime-stamped fields
(`patch_path`, `patch_sha256`, `revision`) with an explicit do-not-set note,
and check/finalize responses shall echo the finding, publication, and
thread-outcome counts they read. Previous findings receive one compact row with a short name, localized
result, and next action; detail and commands stay together, not under unrelated
sections. Metadata and label delta stay compact; exhaustive applicability,
unresolved labels, and removal reasons stay private. SemVer distinguishes MR
contribution from accumulated release impact, selects compatibility labels from
the MR contribution, establishes policy from project evidence, and reports a
reasoned target fallback without a fabricated release estimate. Equivalent labels
prefer namespaced catalog entries without hardcoded alias names.

Manual publication shall have no persistent locks, reservations, receipts, TTL,
automatic freshness reads, polling, or automatic retries. A send exposes its exit
code and bounded redacted diagnostics. Every shell block that creates a comment
or discussion or changes thread state shall start with a head check that uses
the selected MR hostname, requires a successful GET, validates the response,
compares the current MR head with the reviewed head by digest, and stops the
whole block before any write when the request fails, the response is malformed,
or the head moved. The check runs at manual execution time, never during runbook
preparation, and does not depend on `pipefail`. Reply and resolve/reopen share
one annotated shell block; state changes require a successful reply. A
plain-comment POST uses the actual returned discussion ID and resolvability,
closing completed assessments only, never unanswered questions or defects.
The user verifies GitLab and chooses repetition. Timeouts or interruption may
leave accepted remote requests and repetitions may duplicate them; this risk is
visible but does not create a persisted block.

The Python runtime has no terminal UI or in-application publication action.
Preparing a runbook requires the reviewmatic backend; its finished direct
`glab` commands execute without reviewmatic. See
[REQ-F-548](../../requirements/functional/README.md#req-f-548---verify-gitlab-workflows-against-a-persistent-local-ce-server)
for the live-server acceptance boundary.
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
A `full` or `incremental` local review may run the same panel through
`record-participants --bundle`, per-critic `record-critic --bundle --participant`, and `record-arbitration --bundle`: the arbitrator's receipt
carries the merged findings with stable prior IDs, the consolidated checks,
assessment, and the derived verdict; the finalized report artifact stays
schema-identical while the receipts, the selection, and the arbitration
receipt are preserved verbatim as private companions, and the runtime rejects
a receipt without a verdict for every candidate or contradiction. `unchanged`
local evidence runs without a panel.

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
Markdown fences, field diagnostics, manual head-guard failure modes, direct
writes without extra GETs or publication state, errors and repetition, and review
worktree preparation: the arbitration receipt requires exactly one merge verdict
from the decline/push-back/merge-then-fix/merge ladder and the plan, runbook,
summary, and chat render it; a receipt without the verdict or with an unknown
value is rejected; and the exact-git context measures the real merge-base delta
locally and omits it when the merge base is unverified.
fork sources under arbitrary remote names, unrelated or missing repositories,
dirty source and occupied or foreign worktrees, new heads with active and
finalized reviews, same branch names in different projects, concurrent runs,
fetch failures with recovery, revision mismatch, preservation of the user's
checkout, and the absence of per-file code fetches. Discussion-integrity
regressions feed an empty note body and a rootless discussion and assert
addressed loud refusals that write no review context artifact. Context
package regressions cover both modes, direct and automatic invocation
material, skipped context,
contradictory sources, resolved threads without proof, missing critic answers,
multi-critic authorship and contradictions, canonical digest stability across
background edits, supersedes lineage, stale snapshot bindings, and GitLab-free
recording. Mechanical-assembly regressions cover the scope overview with
author-claim flags and GitLab-free re-printing, the ready critic task,
section upsert with machine-field preservation, semantic thread updates by id
with preserved url/state/note bindings and rejected forged bindings, rejected
unknown fields and
envelope wrappers leaving the draft unchanged, verbatim receipt import,
stale-answer rejection with the expected context version, envelope
unwrapping, a complete MR cycle through the new interface, and a local cycle
through `record-input` without GitLab state. The run-panel composition runs
through the public CLI: a mixed OCR and model panel completes from `run --participants` to `plan_ready`, the OCR critic executes mechanically with
its recorded provider and model, the model receipt imports through
`record-run-critic`, the aggregate receipt carries both contributors, the
unanswered poll prints the selection template, and unknown, OCR, and reused
participants are refused. CI-evidence regressions run a pipeline with a
failed bridge whose trace endpoint is unavailable and assert complete
evidence, a collected downstream pipeline, empty pipeline errors, and no
bridge trace request; run-loop regressions keep the evidence permanently
incomplete and assert the bounded loud stop with the collected errors and a
surviving resume state; runtime-identity regressions cover the defensive
commit resolution from install metadata and the self report. Malformed-shape
regressions feed
`null`, non-array, and `null`-entry lists to MR and local `record-input` and
`record-critic` and assert addressed diagnostics with an untouched draft.
Publication-skeleton regressions render the variant catalog, substitute the
judgment of chosen variants (general patch, positioned suggestion, existing
thread, a rejected finding), materialize the patches exactly as the runtime
does, and assert both validators accept on the first pass; unfilled variants
and every documented rule refusal assert their named messages, and duplicate
list identities in one arbitration receipt are rejected with addressed
guidance. Local merge regressions run two sequential critic imports, a repeated
identical result, a conflicting same-identity result, and a finalization that
stays blocked until a verification preserves the original `not_verified`
answer. Local lifecycle regressions run the documented command order through
the public CLI — including repeated `scope-review` over an unfinished draft,
a finalized baseline, and the next snapshot — and assert the draft rebinds to
the new evidence digest without manual repair. Local scope regressions
cover staged, unstaged, and untracked sections separately and together,
compensating staged and unstaged changes, explicit empty-scope results, missing,
ambiguous, and unrelated comparison refs, branch reviews bound to an explicit
ref, repeated runs that retain the agreed boundary, linked-worktree checkouts,
and preparation without any remote that preserves HEAD and the index. Generated
runbook blocks use fake glab to prove that a matching head permits reply plus
resolve/reopen, while a moved head, malformed response, or failed GET permits no
write; GET and writes stay on the selected MR hostname. Backend worktree checks
remain mandatory. Tests use synthetic GitLab responses, never live publication.
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
locally while preserving findings and original critic receipts. Runtime commands
use the selected Git source through `uvx --from`; publication commands remain
direct `glab` commands copied from the runbook.

## Example

An MR contribution assessed as patch selects its unique catalog compatibility
label and prepares a direct manual label command. A wording correction later
updates `runbook.md` without launching another code review.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
