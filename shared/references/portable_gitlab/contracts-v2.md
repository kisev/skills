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
MR and release publication plans may contain a read-only `label_review`. It maps
closed semantic roles and values to unique labels from the complete project and
inherited-group catalog, preserves unknown labels, and records only an add/remove
delta. Concrete label names are catalog results, never policy constants.
New code-review findings record severity, risk, exact evidence, consequence,
relation to the reviewed change, and a minimum fix. Legacy ID-only findings
remain readable for existing v2 artifacts but cannot create a new review plan.
Review contracts 2 and 3 also contain an evidence-derived MR metadata assessment,
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
Publication bodies carry hidden stable-ID markers. Marker text is untrusted
unless it matches the authenticated current user, exact MR, and finalized local
baseline.

Each new plan carries cumulative finding and trusted-publication ledgers. Closed
findings remain addressable and cannot silently reuse an ID. A trusted marker
binds its complete body digest and GitLab note, discussion, or issue location.
Contract 2 stores closed structured actions rather than shell pipelines. Each
short `review_publish.py apply` command confirms one action digest. The helper
rechecks bounded artifacts and live actor, target, refs, catalog, labels, marker,
and conversation state; invokes `glab` with inherited environment, argv, and no
shell; and records an atomic local receipt. It writes progress and bounded,
redacted method, endpoint, exit-code, HTTP-status, stderr, and stdout diagnostics
to stderr while keeping the final JSON on stdout. A definitive non-mutating 4xx
rejection records digest-bound retry evidence. Timeout, 5xx, and unknown results
remain uncertain and cannot be replayed. Repeating the same command verifies an
exact marker and performs only a pending idempotent thread-state phase after a
posted reply. A legacy `phase=unknown` receipt without diagnostic evidence may
retry only after a complete exact marker or label-state absence check; a
completed action is never reopened after remote drift.

The immutable review-plan envelope embeds the complete Markdown. A successful
scaffold atomically replaces the target-scoped `review-publication.md` and a
private pointer to that immutable plan. Contract 1 command plans remain readable
as baselines but are never executable by the structured helper. Contract-2
structured actions remain executable, but contract-1 and contract-2 plans fall
back to a full review rather than becoming a contract-3 incremental baseline. Exact refs live
in private evidence and preflight JSON; the user-facing plan does not display raw
commit SHAs. Prepare and review never invoke helper actions. MR state is recorded
but does not suppress actions for merged or closed MRs.

`finalize_report` contains exact evidence digest and fingerprint. MR preparation
also binds it to the exact publication plan digest. A critic receipt for an
incremental review additionally binds the incremental-delta digest.
`review_decision` binds a fresh report and gives every finding `accept` or
`reject` with a reason.
`release_readiness` binds range/SHA, SemVer, compatibility, migration, rollback,
and CI gates; `ready` needs complete evidence and closed gates.

v1 artifacts may only be read and used to finalize the compatible old workflow.
They cannot be migrated, overwritten, or used as new v2 artifacts.

Earlier v2 review contexts, publication previews, and review plans remain
schema-readable for their original finalized workflow, but they have no
`review_contract_version` and can never become an incremental baseline.
