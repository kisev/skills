---
name: project-release
description: Use when the user explicitly asks to prepare or publish a stable release, cut a maintenance branch, or patch a released line of this repository.
---

# Project Release

Prepare and publish one stable repository release. Never choose the release
version or start this workflow without an explicit user request.

## Branch And Channel Model

- `dev` is the integration trunk: direct commits by default, feature/fix
  branches and pull requests into `dev` only when they help.
- `main` changes only through pull requests with a merge commit and tracks the
  latest stable feature line.
- A stable tag `vX.Y.Z` publishes from the tagged commit: reachable from
  `origin/main` it publishes npm `latest` and the Pages root; reachable only
  from `origin/release/vX.Y` it publishes the npm `vX.Y` dist-tag without
  touching the Pages root.
- `release/vX.Y` maintenance branches exist only for feature lines that are no
  longer the latest; they are cut when the next feature release ships.

## Preconditions

- Ask for the exact stable `X.Y.Z` when the user did not provide it.
- Require a clean worktree: on `dev` for a regular release, or on a release
  prep branch cut at the maintainer-selected commit when the release point is
  not `dev` head.
- Fetch tags and inspect `git status`, the latest stable tags, package
  manifests, both changelogs, and the commits since the latest stable tag.
- Reject an existing local or remote `vX.Y.Z` tag and any published package
  version. Never move or overwrite a tag or npm version.

## Prepare The Release Commit

1. Update the portable package, OpenCode package, and both lockfile version
   mirrors to the user-selected `X.Y.Z`.
2. Add matching dated release headings and evidence-based notes to
   `CHANGELOG.md` and `CHANGELOG.ru.md`, moving the entries that ship into the
   `X.Y.Z` section. Do not invent changes.
3. Run `task format`, `task generate:check`, and `task pre-push`. When building
   release artifacts for a maintenance patch locally, also export
   `RELEASE_DIST_TAG=vX.Y`; CI derives the channel from the tagged commit.
4. Show the exact diff, checks, commit message, and the intended push.
5. Request explicit confirmation before committing and pushing the release
   branch.

## Promote To Main

1. Prepare the exact GitHub pull request base, head, title, and body. Request
   explicit confirmation before creating or updating the PR; do not publish an
   unconfirmed description.
2. Create or update one pull request into `main` with a merge commit: a feature
   release from `dev` or the release prep branch, a latest-line patch from
   `dev` or a `fix/*` branch.
3. Wait for required checks and verify the PR still points at the prepared
   release commit.
4. Show the PR, exact merge method, resulting version, and publication effect.
5. Confirm that no stable or dev publication is running or pending, then request
   explicit confirmation before merging with a merge commit.
6. Fetch `origin/main`, verify the merge commit contains the prepared release
   tree, and run `RELEASE_TAG=vX.Y.Z RELEASE_REVISION=<main-head> task
   release:check -- --require-clean` in a clean checkout of that commit.

## Tag And Publish

1. Show the exact annotated tag action, target commit, and the resolved channel
   effects: npm `latest` with the Pages root from `main`, or the npm `vX.Y`
   dist-tag without Pages from a maintenance branch.
2. Request explicit confirmation before creating the annotated `vX.Y.Z` tag.
3. Request separate explicit confirmation before pushing the tag. A local tag
   does not authorize publication.
4. Recheck that no publication run is active or pending. Resolve the channel
   with `RELEASE_TAG=vX.Y.Z RELEASE_REVISION=<commit> task release:channel` and
   push only the exact tag when it matches the expected channel.
5. Follow `.github/workflows/publish.yml` through completion. Report Pages, npm,
   and GitHub Release verification separately; do not replace a failed release
   with another version unless the user chooses a real corrective release.

## Maintenance Branches And Old-Line Patches

- Cut `release/vX.Y` from the previous line's latest `vX.Y.z` tag when the next
  feature release ships, then bring the publication automation in the branch up
  to date (cherry-pick or merge the workflow and script changes): tag pushes run
  `.github/workflows/publish.yml` from the tagged commit, so a stale workflow
  would publish an old-line patch as `latest`.
- Patch an older line through a `fix/*` pull request into `release/vX.Y`, then
  tag its merge commit; the patch publishes under the npm `vX.Y` dist-tag and
  never redeploys the Pages root.
- Maintenance lines have no support deadlines; cut and patch them on demand.

## Boundaries

- A merge into `main` is not release authorization. Only the confirmed tag push
  starts stable publication.
- Automatic `dev` snapshots do not determine or reserve a stable SemVer.
- Do not push, merge, tag, publish, change repository settings, or retry a
  mutation without the confirmation required for that exact action.
- Preserve unrelated worktree changes and stop if they overlap release inputs.
