---
name: project-release
description: Use when the user explicitly asks to prepare or publish a stable release of this repository from dev to main.
---

# Project Release

Prepare and publish one stable repository release. Never choose the release
version or start this workflow without an explicit user request.

## Preconditions

- Ask for the exact stable `X.Y.Z` when the user did not provide it.
- Require the worktree to be on `dev`, clean, and synchronized with `origin/dev`.
- Fetch tags and inspect `git status`, the latest stable tags, package manifests,
  both changelogs, and the commits since the latest stable tag.
- Reject an existing local or remote `vX.Y.Z` tag and any published package
  version. Never move or overwrite a tag or npm version.

## Prepare On Dev

1. Update the portable package, OpenCode package, and both lockfile version
   mirrors to the user-selected `X.Y.Z`.
2. Add matching dated release headings and evidence-based notes to
   `CHANGELOG.md` and `CHANGELOG.ru.md`. Do not invent changes.
3. Run `task format`, `task generate:check`, and `task pre-push`.
4. Show the exact diff, checks, commit message, and intended `dev` push.
5. Request explicit confirmation before committing and pushing `dev`.

## Promote To Main

1. Prepare the exact GitHub pull request base, head, title, and body. Request
   explicit confirmation before creating or updating the PR; do not use another
   source branch or publish an unconfirmed description.
2. Create or update one pull request whose base is `main` and head is `dev`.
3. Wait for required checks and verify the PR still points at the prepared
   release commit.
4. Show the PR, exact merge method, resulting version, and publication effect.
5. Confirm that no stable or dev publication is running or pending, then request
   explicit confirmation before merging with a merge commit.
6. Fetch `origin/main`, verify the merge commit contains the prepared release
   tree, and run `RELEASE_TAG=vX.Y.Z RELEASE_REVISION=<main-head> task
   release:check -- --require-clean` in a clean checkout of that commit.

## Tag And Publish

1. Show the exact annotated tag action, target `origin/main` commit, and the
   stable effects: Pages root, npm `latest`, and GitHub Release.
2. Request explicit confirmation before creating the annotated `vX.Y.Z` tag.
3. Request separate explicit confirmation before pushing the tag. A local tag
   does not authorize publication.
4. Recheck that no publication run is active or pending. Push only the exact tag
   after proving its peeled commit equals `origin/main` HEAD.
5. Follow `.github/workflows/publish.yml` through completion. Report Pages, npm,
   and GitHub Release verification separately; do not replace a failed release
   with another version unless the user chooses a real corrective release.

## Boundaries

- A merge into `main` is not release authorization. Only the confirmed tag push
  starts stable publication.
- Automatic `dev` snapshots do not determine or reserve a stable SemVer.
- Do not push, merge, tag, publish, change repository settings, or retry a
  mutation without the confirmation required for that exact action.
- Preserve unrelated worktree changes and stop if they overlap release inputs.
