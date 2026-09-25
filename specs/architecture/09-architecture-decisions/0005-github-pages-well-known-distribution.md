# ADR-0005: GitHub Pages Well-Known Distribution

- Status: accepted
- Date: 2026-09-14
- Status changed: none
- Supersedes: [ADR-0001](0001-direct-git-self-contained-skills.md)
- Superseded by: none

## Context and problem statement

Portable skills must be autonomous after installation while canonical shared
contracts and runtimes remain deduplicated in the authored Git tree. The
`skills` CLI does not execute a repository build hook during installation.

## Decision drivers

- Self-contained portable archives from deduplicated authored sources.
- Content integrity, one update source, and verifiable release provenance.
- No install-time build hook or OpenCode package dependency.

## Considered options

- Publish a well-known Pages index and content-addressed archives.
- Commit generated skill copies.
- Use install-time build hooks.
- Publish only direct GitHub Release archive URLs or a generated Git repository.

## Outcome

On an exact validated release tag, build every complete skill in isolation and
deploy a standard agentskills.io well-known index plus one SHA-256-bound archive
per skill to GitHub Pages. The root Pages URL is the stable installation and
update source; the additive `/dev` source follows
[ADR-0011](0011-dev-integration-channel.md). Git tags remain stable provenance and
the OpenCode npm package remains separate.

## Consequences

### Positive

- Authored sources stay deduplicated while published archives are self-contained and content-addressed.

### Negative

- Release CI and GitHub Pages availability become part of publication.

## Compatibility

Historical release tags retain their original direct-Git contract; current consumers use the Pages source.

## Migration

Existing Git-based installations require one rebinding by repeating `skills add` with the Pages URL.

## Rollback

Publication accepts only exact preflighted bytes; historical immutable tags remain the recovery boundary.

## Reversibility

Replacing Pages would require a new stable source, consumer rebinding contract, and superseding ADR.

## Risks

- Pages availability affects installation; content addressing and release verification detect stale or corrupted bytes.

## Links

- Requirements: [REQ-F-004](../../requirements/functional/README.md#req-f-004---publish-one-verified-release), [REQ-I-001](../../requirements/interfaces/README.md#req-i-001---skill-interface), [REQ-Q-005](../../requirements/quality/README.md#req-q-005---reproducible-distribution), [REQ-Q-008](../../requirements/quality/README.md#req-q-008---verify-release-promotion), [REQ-C-002](../../requirements/constraints/README.md#req-c-002---portable-distribution-boundary)
- Related ADRs: [ADR-0001](0001-direct-git-self-contained-skills.md)
