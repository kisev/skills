# Release-aware SemVer

The defect review stays bound to the merge request's exact base and head. The
SemVer comparison basis is separate: the last published release of the affected
line, plus accumulated target-branch changes and the merge request's own
contribution.

## Establish the release policy

Read project instructions, release documentation, version manifests,
changelogs, CI publishing jobs, and release-tool configuration at the exact
reviewed refs. Identify what counts as a publication, which component and line
the merge request affects, and how stable releases and prereleases differ.

A default branch name is no proof of release policy. The newest or highest tag
is not automatically the baseline. A tag is published only when the project's
policy says so; an upcoming release, draft, failed publication, or unrelated
component tag is no baseline.

Select the latest confirmed publication on the relevant line and explain the
policy, line selection, and evidence in the runbook.

## Two assessments

- The **merge request contribution** describes the change's own effect on the
  published contract. It selects the compatibility label.
- The **next release impact** describes the release after including the merge
  request, including accumulated target changes.

Inspect the released tree, the target branch, and the merge request diff.
Compare public behavior, not commit titles or the largest historical label;
trace reverts and interactions. Never change the checkout or run project
publishing jobs to infer policy.

Examples:

- The target already breaks a released API and the merge request fixes a
  compatible bug: next release `major`, contribution `patch`.
- The target introduces an unreleased API and the merge request changes it
  incompatibly: this alone is not `major`; assess the final addition against
  the released contract.
- The merge request removes a pending breaking change: reassess the final
  contract instead of keeping `major` mechanically.

For independently versioned components, name each affected component. Follow
documented pre-1.0 and prerelease conventions. `not applicable` requires
evidence that no versioned contract exists, not merely missing release
information.

## Explicit fallback

When the policy, publication, relevant line, or combined comparison cannot be
established reliably, keep the review running on an explicit target fallback.
State exactly what could not be established and why, and assess the merge
request relative to its target branch. Never describe the fallback as the next
release's SemVer.
