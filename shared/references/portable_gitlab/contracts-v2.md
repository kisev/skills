# Private GitLab Artifact Contracts v2

New evidence snapshots, release inventories, context packages, publication
plans, analysis reports, release readiness reports, and finalize reports are
immutable content-addressed JSON envelopes `portable-gitlab/<kind>/v2`.
Private state uses `0700` directories and `0600` files; SHA-256 stdout covers
the full envelope.

Collection identity is `hostname`, resolved GitLab `project_id`, object kind,
and IID. A profile is only a producer and does not create another collection.

The schema validates every kind/payload pair. Every payload records
`external_mutations=false`. `evidence_snapshot` records `base_sha`, `start_sha`,
and `head_sha`. `release_inventory` binds an exact evidence snapshot and
tag-to-head commit range. `context_package` binds a goal, acceptance criteria,
claims, prior decisions, open questions, and a thread registry to one evidence
digest. `publication_plan` binds its evidence digest. `analysis_report` records
`run_id`, `session_id`, and findings bound to the selected evidence.

Release and legacy MR publication plans may contain a semantic `label_review`.
It maps closed semantic roles and values to unique labels from the complete
project and inherited-group catalog, preserves unknown labels, and records only
an add/remove delta. Concrete label names are catalog results, never policy
constants.

New ordinary MR plans use the same exhaustive applicability assessment,
retaining unresolved labels and requiring evidence for removals. Their
`mr_content` binds locale, template selection, preservation assessment,
metadata-edit summary and SemVer rationale. `requests` stores exact immutable
JSON payloads and explicit-host manual `glab` commands. Title and description
requests contain only changed fields; labels use add/remove delta. No command is
executed by a runner. Legacy MR plans remain readable but require fresh
preparation before finalize. Release preparation retains its existing content
contract.

Failed-job trace collection streams response headers and content under one
absolute deadline and a hard byte bound. It terminates the child process group
on timeout, overflow, or collection failure, and reports unsupported POSIX
streaming capabilities as a controlled workflow error.

Issue-link listing is a whole-collection REST API, not a paged list. Collectors
accept its complete single response even at CE's 100-link boundary, where
`page` and `per_page` are ignored. Other resources still reject repeated pages
and protective-limit exhaustion; this compatibility rule does not relax their
completeness checks.

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

Release preparation splits immutable evidence from a stable user-facing result.
A complete scaffold atomically replaces the target-scoped
`release-publication.md` and writes `release-publication.json` last as the
pointer to the exact immutable plan. Finalization binds that pointer to the
scaffold binding and rejects superseded or modified plans. Incomplete scaffolds
do not replace the previous stable result. The release inventory also binds
component-MR approvals and conversations, contributor and reviewer candidates,
milestone candidates, and bounded work-item evidence. Release content records
the approved people and milestone, illustration preset, and one
rationale-backed decision for every candidate work item.

The pre-merge release plan contains manual `glab` commands only. A read-only
`post-merge` transition verifies the merged MR, refreshes evidence and inventory,
then atomically replaces the same stable runbook with commands bound to the
exact publication SHA. Request bodies and long content remain immutable and
content-addressed. Neither phase executes a remote mutation. The announcement
command retains its illustration attachment without `--unique`, which glab
forbids with `--attach`. It does not promise remote deduplication; the runbook
requires checking the target discussion before repetition.

Contract 6 adds required `semver_assessment` to the content and plan. Existing
`semver_impact`/`semver_rationale` describe only the MR contribution and select
its compatibility label. The new assessment binds release policy and sources,
the selected catalog release/tag name and commit, current target branch/commit,
and a distinct accumulated next-release impact/rationale. `target_fallback`
requires a reason and null release fields. If current target lookup failed,
`target_revision=mr_snapshot` explicitly identifies the MR start snapshot.

`finalize_report` contains exact evidence digest and fingerprint. MR preparation
also binds it to the exact publication plan digest. `release_readiness` binds
range/SHA, SemVer, compatibility, migration, rollback, and CI gates; `ready`
needs complete evidence and closed gates.

v1 artifacts may only be read and used to finalize the compatible old workflow.
They cannot be migrated, overwritten, or used as new v2 artifacts.

The retired review and local-WIP artifacts (`review_context`, `review_plan`,
`review_decision`, `critic_receipt`, `local_wip_snapshot`, and
`local_review_report`), the `code-review` profile, the `local` target scope,
`local_fix` outcomes, and the `code-review/publication-action/v1` publication
action are not part of this contract. A supplied retired artifact or field is
rejected as an unknown profile, kind, or field. There is no compatibility
mode, alias, or migration; historical artifacts remain available only in Git
history.
