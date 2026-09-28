# ADR-0014: Change-linked documentation review

- Status: accepted
- Date: 2026-09-28

## Context and Drivers

Documentation and canonical contracts can drift despite passing format and locale
checks. Complete reviews repeatedly reconstruct dependencies, while rewriting
guides can lose valid prerequisites and recovery details. The target is portable
change assessment and reusable evidence, with clear limits on what automation proves.

## Considered Options

1. Improve prompts alone. This is inexpensive but leaves impact selection and
   previous decisions entirely dependent on the current conversation.
2. Add minimal document dependencies and private snapshot-bound review results.
   This makes changed evidence visible without claiming semantic correctness.
3. Require an OpenCode completion hook and hashes in every document. This couples
   portable behavior to a host and creates manual metadata churn.

## Decision

Select option 2 as required by
[REQ-F-519](../../requirements/functional/README.md#req-f-519---maintain-change-linked-documentation-and-reusable-review-evidence).
Source globs and canonical owners live in optional document frontmatter; the
reverse relation and source digests are computed. Unmapped changes require
assessment. Private results retain findings, decisions, and unchecked boundaries.
Full review keeps one independent critic; incremental and unchanged reviews
reuse applicable evidence without reopening accepted risks automatically.

Use review consistently in public checking interfaces. The specification mode is
`spec-review`; the old explicit mode is unsupported, without a compatibility alias.
Natural-language specification checks continue to select the review mode.

## Consequences, Compatibility, and Recovery

Agents must maintain dependency declarations and assess missing relations.
Structural checks cannot prove that a declared dependency set is complete or a
semantic conclusion correct. Source changes reject stale finalization. The
private store contains paths and hashes rather than source bytes; report authors
remain responsible for excluding secrets. No host plugin or credentials are needed.

Existing projects without metadata or prior results still work: the first review
is full and unannotated changes remain explicit. Users of the removed explicit
mode must update their invocations. Private review records may be removed by the
user; rebuilding them requires a new full review. Reverting the implementation
leaves maintained Markdown readable and private state isolated from product data.

## Verification and Related Decisions

Dependency selection, stale results, retained findings, limitations, and critic
identity are checked by `tests/test_documentation_review.py`. Translation checks
compare metadata. Semantic review checks preserved detail and scope, not only
valid JSON. This extends the evidence ownership of
[ADR-0010](0010-separate-review-and-publication.md) without adding publication behavior.
