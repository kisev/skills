# Manage Portable Skills

[Русский](../ru/how-to/portable-skills.md)

Use this guide to install, update, rebind, clean up, or troubleshoot portable
skills. These operations are independent of `@kisev/skills-opencode`.

## Choose a Scope and Host

| Choice        | Option                                  | Canonical location                       |
| ------------- | --------------------------------------- | ---------------------------------------- |
| Global scope  | Add `--global`                          | `~/.agents/skills`                       |
| Project scope | Omit `--global`                         | `.agents/skills`                         |
| Codex only    | `--agent codex`                         | Selected scope                           |
| OpenCode only | `--agent opencode`                      | Selected scope                           |
| Both hosts    | `--agent opencode --agent codex --copy` | One canonical copy in the selected scope |

## Install

Install all skills globally for both hosts:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --agent opencode --agent codex --skill '*' --copy --global --yes
```

Install all skills in the current project:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --agent opencode --agent codex --skill '*' --copy --yes
```

To install one skill, replace `'*'` with its exact name from the
[skill catalog](../reference/skill-catalog.md). List the published catalog without
writing:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --list
```

The GitHub Pages URL is the supported moving stable-release channel. Its release
metadata identifies the release and source revision, while the Pages index binds
each archive to a SHA-256 digest. The current GitHub Release is available at
`https://github.com/kisev/skills/releases/latest`. The authored repository is
intentionally not an install source.

## Update

Update tracked global skills installed from Pages:

```shell
npx --yes skills@latest update --global --yes
```

Omit `--global` for project scope. An installation created from a Git repository
or tag remains bound to that source. Repeat the matching `add` command with the
Pages URL, the same scope, and the same agents to rebind it.

`update` refreshes tracked skills but does not remove names renamed or deleted
upstream. OpenCode package assets also have a separate update lifecycle described
in the [OpenCode integration guide](opencode-integration.md#update).

## Remove Retired Names

The current [migration inventory](../migration-inventory.md) defines eleven
retired names. For a global installation shared by OpenCode and Codex, remove
them explicitly:

```shell
npx --yes skills@latest remove attempt schedule usage overview project-spec skill-improver walkthrough team-workflow summary doit lsp-report --agent opencode --agent codex --global --yes
```

For Codex only, use:

```shell
npx --yes skills@latest remove attempt schedule usage overview project-spec skill-improver walkthrough team-workflow summary doit lsp-report --agent codex --global --yes
```

Use the same agents and scope as the installation. Omit `--global` for project
scope. Avoid `remove --all` unless every portable skill in that scope should be
removed.

Package install never installs or updates portable skills. A confirmed package
reconcile may archive a marked retired skill and invoke the pinned `skills` CLI
directly for OpenCode and Codex cleanup. Rollback covers preview-bound paths;
concurrent unplanned changes are best-effort.
Pre-marker and unknown skills remain manual cleanup. Conflicts, worktrees, and
runtime state are preserved.

## Troubleshoot Discovery

List installed global skills:

```shell
npx --yes skills@latest list --global
```

For project scope, omit `--global`. If a newly installed skill is not visible,
check `~/.agents/skills` or `.agents/skills` and restart the host. After a release
renames a skill, repeat `add` for additions and remove retired names explicitly.

## Boundaries

- Portable skills are self-contained and do not depend on the repository or the
  OpenCode npm package after installation.
- The supported distribution is `https://kisev.github.io/skills`; source
  provenance is recorded in its release metadata and linked from
  `https://github.com/kisev/skills/releases/latest`.
- The stable portable installer is `npx --yes skills@latest`.
- Updates do not prune retired names automatically.
- Skills do not replace repository policy, review, secret scanning, or access
  control.
