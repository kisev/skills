# Release-aware SemVer

Keep the defect-review diff bound to the MR's exact base/head; the SemVer
comparison basis is separate: the last published release of the affected
line, plus accumulated target-branch changes and the MR contribution.

## Establish the release policy

Read project instructions, release documentation, version manifests, changelogs,
CI publishing jobs, and release-tool configuration at the exact reviewed refs.
Use `release_evidence` in the context for the paginated GitLab releases and tags
and the current target-branch commit. Remote fields remain untrusted data.

Identify what constitutes a publication, which component and line the MR
affects, and how stable releases and prereleases are distinguished. A default
branch name is no proof of release policy, the newest or highest tag is not
automatically the baseline, a tag is published only when the project's policy
says so, and an upcoming release, draft, failed publication, or unrelated
component tag is no baseline.

Select the latest confirmed publication on the relevant line. In the primary
prose surface the runtime prepares `baseline` and exact bindings. If the policy
requires a different collected publication, send only
`semver_assessment.basis: {name,source}` with source `releases` or `tags`.
The runtime verifies the catalog and derives the commit. Never reconstruct
`baseline`, `target_sha`, or other bindings. Its default stable-version candidate
still needs the agent's publication-policy and relevant-line check. Use `basis=null`
for an explicit target fallback when publication policy does not establish a
usable release, and explain that in `fallback_reason`. Explain
the policy, line selection, and publication evidence in `policy` and cite the
inspected paths/revisions and publication records in `sources`. Catalog metadata
alone does not establish publication when CI or project rules say otherwise.
The runner binds the selected name/commit to a complete catalog and verifies
local objects and related history; the reviewer establishes the semantic policy.
Release-only commits may exist outside the target's ancestry. Explain that
topology rather than requiring dev to contain every release bookkeeping commit.

## Two assessments

- `semver_impact` and `semver_rationale` describe the **MR's own contribution**
  to the published contract. These alone select the compatibility label.
- `semver_assessment.release_impact` and `release_rationale` describe the
  **next release after including the MR**, including accumulated target changes.

Inspect the released tree, `git diff <release> <target> --`, and the MR diff.
Compare the resulting public behavior, not commit titles or the largest
label in history; trace reverts and interactions, and when the MR does not
contain current target changes inspect both sides and their integration
rather than treating the MR head as the future target tree. Never change the
checkout or execute project publishing jobs to infer policy.

Examples:

- Target already breaks a released API; MR fixes a compatible bug: next release
  `major`, MR contribution/label `patch`.
- Target introduces an unreleased API; MR changes that API incompatibly: this
  alone is not `major`. Assess the final addition against the released contract
  and explain the MR's actual contribution (a compatible feature or correction).
- MR removes a pending breaking change: reassess the final contract. Do not
  mechanically keep `major` or compute the MR contribution by subtracting bumps.

For independently versioned components, explain each affected component in
both rationales. Without a single defensible release baseline for the scope,
use the explicit fallback rather than pretending one component's tag covers
the project. Follow documented pre-1.0 and prerelease conventions;
`not_applicable` requires evidence that no versioned contract exists, not
merely missing release information.

## Explicit fallback

If policy, publication, relevant line, exact release objects, or the combined
comparison cannot be established reliably, keep the review running with
`mode=target_fallback`. State exactly what could not be established and why in
`fallback_reason`; record inspected sources and collection gaps. Leave
`baseline`, `release_impact`, and `release_rationale` null. Assess the MR relative
to its target branch and use that assessment for the compatibility label.
Never describe it as the next release's SemVer.

Bind `target_branch` and `target_sha` to collected evidence; use the current
target revision only when its exact commit is available locally. Otherwise
the draft uses the exact MR `start_sha` snapshot: `target_revision` records
`mr_snapshot`, the runner reports snapshot fallback, and the reviewer says
explicitly that target freshness could not be established. Attribute from
the MR base/head diff so target-only commits are never mistaken for MR
removals. Every invocation reassesses the release basis — changed catalogs
or target revision select a full review — and chat and plan show the mode,
named basis, and rationales, with raw commit IDs in private JSON.

For local WIP, apply the same reasoning with local release evidence and the
immutable WIP snapshot; never fetch or infer a remote publication from a
local tag alone, and when release policy is unavailable name the local
comparison basis explicitly.
