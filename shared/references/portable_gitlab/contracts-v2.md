# Private GitLab Artifact Contracts v2

New evidence snapshots, release inventories, review contexts, publication and
review plans, analysis reports, critic receipts, review decisions, release
readiness, and finalize reports are immutable content-addressed JSON envelopes
`portable-gitlab/<kind>/v2`. Private state uses `0700` directories and `0600`
files; SHA-256 stdout covers the full envelope.

Collection identity is `hostname`, resolved GitLab `project_id`, object kind, and
IID. A profile is only a producer and does not create another collection.

The schema validates every kind/payload pair. Every payload records
`external_mutations=false`. `evidence_snapshot` records `base_sha`, `start_sha`,
and `head_sha`; `local_wip_snapshot` records ref plus committed, staged, unstaged,
and untracked sections. `release_inventory` binds an exact evidence snapshot and
tag-to-head commit range. `review_context` binds current-user role, complete
threads and notes, trusted current-user publication markers, GitLab-only
incremental selection, and read-only local Git verification to an evidence
snapshot. Incremental metadata keeps exact baseline and delta refs private;
local WIP never has an incremental baseline.
`publication_plan`, `review_plan`, `analysis_report`, and `critic_receipt` bind
their evidence digest; the latter records `run_id` and `session_id`.
Release and legacy MR publication plans may contain a semantic `label_review`. It maps
closed semantic roles and values to unique labels from the complete project and
inherited-group catalog, preserves unknown labels, and records only an add/remove
delta. Concrete label names are catalog results, never policy constants.

New ordinary MR plans instead use the same exhaustive applicability assessment
as code review, retaining unresolved labels and requiring evidence for removals.
Their `mr_content` binds locale, template selection, preservation assessment,
metadata-edit summary and SemVer rationale. `requests` stores exact immutable
JSON payloads and explicit-host manual `glab` commands. Title and description
requests contain only changed fields; labels use add/remove delta. No command is
executed by a runner. Legacy MR plans remain readable but require fresh preparation
before finalize. Release preparation retains its existing content contract.

Failed-job trace collection streams response headers and content under one
absolute deadline and a hard byte bound. It terminates the child process group
on timeout, overflow, or collection failure, and reports unsupported POSIX
streaming capabilities as a controlled workflow error.

MR evidence stores locale and template discovery in `project`. Discovery reads
the project default description and bounded repository templates from an exact
default-branch revision; failure is distinct from absence and is shown as a
limitation. Changes to this evidence invalidate readiness. Successful scaffold
replaces `mr-publication.md` and `mr-publication.json` under a target-scoped lock
with rollback; immutable evidence and requests remain private. Finalize accepts
the stable pointer or exact plan and checks the current pointer, Markdown and
request bodies. Failed scaffolds do not return an old stable path as success.
The displayed freshness command binds the expected evidence, draft and requests
so an older open document cannot accidentally validate a replacement plan.
New code-review findings record severity, risk, exact evidence, consequence,
relation to the reviewed change, and a minimum fix. Legacy ID-only findings
remain readable for existing v2 artifacts but cannot create a new review plan.
Review contracts 2 through 4 also contain an evidence-derived MR metadata assessment,
a closed SemVer impact with rationale, localized presentation labels, a compact
disposition for every previous finding, stable finding revisions, non-blocking
recommended issues, and an exhaustive applicability decision for every exact
project or inherited-group label name and description. The runtime derives the
add/remove delta and requires a unique matching compatibility label for a closed
SemVer impact. Existing-thread outcomes are `no_publication`, `local_fix`,
`reply`, `resolve`, or `reopen`. Contract 3 assigns each actionable finding and
thread correction a closed `fix_mode`: an exact current-line fix uses one
single-line or bounded multi-line `suggestion`; every other actionable fix uses
one textual unified patch. `not_required` is limited to threads without a code
correction. Patches are checked against the exact reviewed head in a temporary
Git index, reject binary, symlink, rename, traversal, and oversized content, and
are stored as immutable private `.patch` files without changing the checkout.
Every new review invocation reassesses every open and resolved discussion and all
of its non-system replies. A resolved thread needs a reply only when it adds
information. Explicitly select `no_publication` when an existing explanation or
applied suggestion is confirmed by current code, regardless of the resolver.
Published patches use one copy-ready `sh` heredoc invoking
`git apply`. A `resolve` or `reopen` action follows, but is separate from, the
action that publishes its explanation.
Contract 4 adds a semantic chat assessment and runner-owned presentation.
Contract 5 binds thread decisions to the complete discussion, including system
notes, retains explicit `unchanged` mode, and enforces assessment-to-state
transitions plus a validated code fix for an accepted thread. A
code-review-owned evidence pointer and target-scoped progress pointer expose
prepared, context, critic, finalize, decision, content, plan, and stale stages
without depending on another profile's shared collection pointer. Generated private drafts bind exact
labels, threads, latest-note digests, critic scope, pipeline state, and prior
artifacts. When the selected mode requires a critic, only a recorded
content-addressed receipt can advance the workflow. Only a fresh contract-5 plan
can render final chat.
Each new plan carries a cumulative finding ledger. Closed findings remain
addressable and cannot silently reuse an ID. Publication bodies are plain files
and the plan provides direct manual `glab` commands that consume them. Incremental
review determines whether content is already published only by reading current
GitLab discussions, notes, and issues authored by the authenticated user and
comparing their meaning. A digest-bound post-success marker records only that a
manual command exited zero locally; it can require remote revalidation but cannot
serve as publication state, a receipt, an idempotency record, or a postcondition.
For contract 5, the review-state activation lock protects only local review
artifacts. A concurrent `prepare` cannot
leave the superseded plan executable.

The immutable review-plan envelope embeds the complete Markdown. A successful
scaffold atomically replaces the target-scoped `review-publication.md` and a
private pointer to that immutable plan. Contract 1 through 5 plans remain readable
as historical baselines, but their helper commands are not executable after the
move to direct manual `glab` commands. Older plans fall back to a full review
rather than becoming a contract-6 incremental baseline. Exact refs live in
private evidence; the user-facing plan does not display raw commit SHAs. Prepare
and review never invoke publication commands. MR state is recorded but does not
suppress actions for merged or closed MRs.

Release preparation uses the same split between immutable evidence and a stable
user-facing result. A complete scaffold atomically replaces the target-scoped
`release-publication.md` and writes `release-publication.json` last as the pointer
to the exact immutable plan. Finalization binds that pointer to the scaffold
binding and rejects superseded or modified plans. Incomplete scaffolds do not
replace the previous stable result. The release inventory also binds component-MR
approvals and conversations, contributor and reviewer candidates, milestone
candidates, and bounded work-item evidence. Release content records the approved
people and milestone, illustration preset, and one rationale-backed decision for
every candidate work item.

The pre-merge release plan contains manual `glab` commands only. A read-only
`post-merge` transition verifies the merged MR, refreshes evidence and inventory,
then atomically replaces the same stable runbook with commands bound to the exact
publication SHA. Request bodies and long content remain immutable and
content-addressed. Neither phase executes a remote mutation.

Contract 6 adds required `semver_assessment` to the content and plan. Existing
`semver_impact`/`semver_rationale` describe only the MR contribution and select
its compatibility label. The new assessment binds release policy and sources,
the selected catalog release/tag name and commit, current target branch/commit,
and a distinct accumulated next-release impact/rationale. `target_fallback`
requires a reason and null release fields. If current target lookup failed,
`target_revision=mr_snapshot` explicitly identifies the MR start snapshot.
Review context collects `release_evidence` without making absent publication
information block review. Refreshing catalogs and the target commit protects
finalization; a changed release basis forces full review on the next invocation.

`finalize_report` contains exact evidence digest and fingerprint. MR preparation
also binds it to the exact publication plan digest. A critic receipt for an
incremental review additionally binds the incremental-delta digest.
`review_decision` binds a fresh report and gives every finding `accept` or
`reject` with a reason. When a critic is required, the decision also binds the
exact recorded critic-receipt digest selected by progress state.
`release_readiness` binds range/SHA, SemVer, compatibility, migration, rollback,
and CI gates; `ready` needs complete evidence and closed gates.

v1 artifacts may only be read and used to finalize the compatible old workflow.
They cannot be migrated, overwritten, or used as new v2 artifacts.

Earlier v2 review contexts, publication previews, and review plans remain
schema-readable for their original finalized workflow, but they have no
`review_contract_version` and can never become an incremental baseline.
