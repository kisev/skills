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
threads and notes, and read-only local Git verification to an evidence snapshot.
`publication_plan`, `review_plan`, `analysis_report`, and `critic_receipt` bind
their evidence digest; the latter records `run_id` and `session_id`.
New code-review findings record severity, risk, exact evidence, consequence,
relation to the reviewed change, and a minimum fix. Legacy ID-only findings
remain readable for existing v2 artifacts but cannot create a new review plan.

`finalize_report` contains exact evidence digest and fingerprint. MR preparation
also binds it to the exact publication plan digest. The plan has a private,
immutable Markdown companion which must match the Markdown in its JSON envelope.
`review_decision` binds a fresh report and gives every finding `accept` or
`reject` with a reason.
`release_readiness` binds range/SHA, SemVer, compatibility, migration, rollback,
and CI gates; `ready` needs complete evidence and closed gates.

v1 artifacts may only be read and used to finalize the compatible old workflow.
They cannot be migrated, overwritten, or used as new v2 artifacts.
