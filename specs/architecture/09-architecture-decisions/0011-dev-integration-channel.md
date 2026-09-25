# ADR-0011: Integrate On Dev And Isolate Publication Channels

- Status: accepted
- Date: 2026-09-25
- Status changed: none
- Supersedes: none
- Superseded by: none

## Context and problem statement

The repository used `main` for integration and stable release preparation.
Users could install only the stable Pages distribution and npm `latest`, which
made pre-release validation depend on a checkout rather than public channels.

## Decision drivers

- Keep stable SemVer and release initiation under explicit maintainer control.
- Let users opt into current development snapshots for both products.
- Prevent either Pages or npm development publication from replacing stable.
- Avoid permanent release branches and per-push GitHub prereleases.

## Considered options

- Integrate on permanent `dev` with isolated moving development channels.
- Keep `main` as the integration branch and publish manual prereleases.
- Use classical GitFlow release and hotfix branches.

## Outcome

`dev` is the integration branch and accepts direct commits plus feature/fix pull
requests. Only `dev` may open a pull request into `main`, and promotion uses a
merge commit. Stable version and changelog changes are prepared on `dev`; the
maintainer explicitly confirms the merge, annotated tag, and tag push.

A push to `dev` triggers the same trusted publication workflow used by stable
tags. After its complete gate succeeds, it deploys a moving Pages `/dev`
distribution and publishes an npm prerelease `<stable>-dev.<run>.g<sha>` under
dist-tag `dev`. The identifier describes a snapshot and does not select a future
stable SemVer. Pages deployments atomically contain stable root and `/dev`; dev
creates no GitHub Release and only the current portable dev snapshot is retained.

## Consequences

### Positive

- Stable publication remains explicit while development builds are installable.
- One workflow identity serves npm trusted publishing for both channels.
- Channel-specific URLs and dist-tags make user opt-in visible and reversible.

### Negative

- A Pages update must fetch and validate the channel it preserves.
- npm retains immutable dev package versions even though `/dev` is moving.
- GitHub branch protection must require the repository CI checks on `main`.

## Compatibility

The stable Pages URL, npm `latest`, stable tags, and existing installations keep
their current meaning. Dev is additive and requires an explicit source or
dist-tag.

## Migration

Create `dev` from the current `main`, make it the normal contribution target,
and configure `main` to require pull requests and CI. Configure npm trusted
publishing for `.github/workflows/publish.yml`; no second publisher is required.

## Rollback

Disable the workflow-run trigger and stop advertising `/dev` and npm `dev`.
Stable publication remains tag-driven.

## Reversibility

Removing `dev` requires rebinding development installations but does not change
stable consumers.

## Risks

- Failed channel preservation can block Pages publication; fail closed rather
  than deploying a partial site.
- Direct pushes to `main` remain an external repository-setting risk; CI rejects
  pull requests whose source is not `dev`.

## Links

- Requirements: [REQ-F-004](../../requirements/functional/README.md#req-f-004---publish-one-verified-release), [REQ-F-009](../../requirements/functional/README.md#req-f-009---publish-an-isolated-development-channel), [REQ-Q-010](../../requirements/quality/README.md#req-q-010---isolate-publication-channels)
- Related ADRs: [ADR-0005](0005-github-pages-well-known-distribution.md)
