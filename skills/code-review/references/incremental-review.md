# Incremental GitLab review

Incremental review applies only to one exact GitLab MR. Local WIP always receives
a fresh full review and never creates or reads an incremental baseline.

## Selection

After `prepare`, run `context` with `--incremental auto` by default. Pass
`--incremental off` only when the user explicitly asks for no incremental
review, asks to start from scratch, or says to ignore the previous review. The
phrase "full review" alone does not disable incremental review and may describe
depth instead.

The first review after this contract is installed is full. Existing legacy
artifacts are not imported. A successful `scaffold-review` atomically publishes
the latest immutable plan as the only baseline for that MR.

Incremental review is independent of `fast`, `normal`, and `deep`. When a
compatible baseline and changed current evidence exist, use mode `incremental`
and do not ask for a depth. Full-review depth selection applies only when no
incremental review is available.

## Eligibility and fallback

Use the baseline only when all of these hold:

- exact GitLab target, authenticated user, and review role match;
- baseline evidence and context are complete and finalized;
- incremental contract versions are compatible;
- base and start refs are unchanged;
- a changed head descends from the baseline head;
- current evidence, discussions, notes, and local Git objects are complete.

Changed base/start refs, non-ancestor history, missing or tampered state,
incompatible contracts, removed baseline discussions or notes, and incomplete
evidence select a full review. This is a normal safe fallback, not permission to
reuse part of an incompatible result.

If code is unchanged but discussions, standalone notes, metadata, the complete
project/inherited label catalog, or CI changed, run an incremental review of
those changes. If nothing changed, return a short no-op result without a critic
or a new review plan.

## Scope

Start technical analysis from `incremental.incremental_delta.changed_paths`, changed
discussions and notes, changed metadata fields, and CI changes. This is a
delta-triggered scope, not a changed-files-only boundary: inspect unchanged
callers, consumers, configuration, and contracts when the delta can affect them.
Do not repeat analysis of the complete historical MR diff.

Fetch and snapshot all current discussions and notes for freshness. Deeply read
new or changed conversations and every conversation needed to revalidate a
previous finding. Do not trust `resolved=true`, an approval, green CI, or a
short "Fixed" response as proof.

## Previous findings

Revalidate every previously accepted finding and recommended issue against the
current code and complete relevant conversation. Give each exactly one current
status:

- `active`: still valid without a changed publication body;
- `fixed`: the current MR removes the problem;
- `withdrawn`: current evidence or an accepted discussion decision invalidates
  the finding;
- `changed`: the same underlying finding needs revised evidence or publication
  text;
- `unverified`: current evidence cannot confirm or reject it.

An `unverified` previous finding prohibits a ready verdict. `active`, `changed`,
and `unverified` findings remain in the current finding set with the same stable
ID. `fixed` and `withdrawn` findings leave the active set but remain in the
previous-finding table. Reconsider a previously rejected critic candidate or
false positive only when the delta or discussion changes its evidence.

Each previous-finding assessment also records `critic_required`. It is mandatory
for `changed` and `unverified`, and for any other status the reviewer considers
disputed. The incremental critic receipt includes all such IDs in
`target_finding_ids`.

Keep every accepted finding and recommended issue in the cumulative private
ledger after it becomes fixed or withdrawn. Preserve its stable ID, latest
revision, record, and status so a later reintroduction is assessed as `changed`
rather than becoming a new finding.

Keep rejected primary and critic candidates in a separate private ledger with
their source, complete finding, rejection reason, and path, thread, metadata, and
CI dependencies. When the incremental delta touches a dependency, assess the
candidate as `still_rejected` or `promoted`; a promoted candidate must appear in
the accepted finding set.

Do not inherit a previous verdict, approval, thread decision, publication body,
or label decision. Recalculate the overall necessity, relevance, architecture,
SemVer, exhaustive label applicability and delta, metadata assessment, and
verdict from the baseline plus current evidence.

## Critic

A changed incremental review requires an independent critic whose receipt binds
the incremental-delta digest. Give the critic the delta and the unchanged
consumers required to evaluate it, but not the primary review's previous
findings. The primary reviewer revalidates previous findings. Ask for a targeted
critic check only when a previous finding becomes changed or disputed.

If an independent critic is unavailable, block the result and do not replace the
baseline. A no-op review needs no critic.

## Stable IDs and publication

New findings and recommended issues start at revision 1. An unchanged active
finding keeps its revision; a changed publication advances it. Thread replies
use a stable ID derived from the root note and advance the revision for each new
prepared reply.

If a prior finding was not published, revalidate it and include its current body
in the new plan. If a trusted marker shows that it was published, update the
existing discussion instead of creating a duplicate. Ambiguous unmarked legacy
text is not adopted automatically.

The baseline pointer, exact refs, delta, previous findings, markers, and digests
remain private technical JSON. User-facing reports omit raw SHAs.
Every regenerated structured action receives an exact digest; confirmation of a
previous action never authorizes a changed publication or label delta.
