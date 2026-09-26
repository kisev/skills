# Manage Portable Skills

[Русский](../ru/how-to/portable-skills.md)

Use this guide to install, update, rebind, clean up, or troubleshoot portable
skills. These operations are independent of `@kisev/agentomatic`.

## Choose a Scope and Host

| Choice | Option | Canonical location |
| - | - | - |
| Global scope | Add `--global` | `~/.agents/skills` |
| Project scope | Omit `--global` | `.agents/skills` |
| Codex only | `--agent codex` | Selected scope |
| OpenCode only | `--agent opencode` | Selected scope |
| Both hosts | `--agent opencode --agent codex --copy` | One canonical copy in the selected scope |

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
`https://github.com/kisev/skills/releases/latest`. The authored `skills/` tree is
intentionally not a public install source; `.agents/skills/project-release` is a
repository-local maintainer workflow.

### Install The Development Channel

Replace the stable source with the explicit `/dev` source:

```shell
npx --yes skills@latest add https://kisev.github.io/skills/dev --agent opencode --agent codex --skill '*' --copy --global --yes
```

The moving dev channel updates after successful pushes to `dev`. Its technical
version identifies the workflow run and source revision; it does not predict the
next stable release. Repeat the stable `add` command to switch an installation
back to stable.

## Update

Update tracked global skills installed from Pages:

```shell
npx --yes skills@latest update --global --yes
```

Omit `--global` for project scope. An installation created from a Git repository
or tag remains bound to that source. Repeat the matching `add` command with the
Pages URL, the same scope, and the same agents to rebind it.

`update` refreshes tracked skills, detects names deleted upstream, and offers to
remove their local copies. OpenCode package assets have a separate update
lifecycle described in the [OpenCode integration guide](opencode-integration.md#update).

## Remove Retired Names

The current [migration inventory](../migration-inventory.md) defines eleven
retired names. Normally, accept their removal when `skills update` reports them.
To remove them explicitly from a global installation shared by OpenCode and
Codex, run:

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

The OpenCode package never installs, updates, inspects, or removes portable
skills. Use `skills update` or `skills remove` for their complete lifecycle.

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
- Cross-skill relations are install recommendations: the build materializes each
  skill's declared companions into its `SKILL.md` "Related skills" section, and
  every archive still works on its own.
- The supported distribution is `https://kisev.github.io/skills`; source
  provenance is recorded in its release metadata and linked from
  `https://github.com/kisev/skills/releases/latest`.
- The opt-in development distribution is `https://kisev.github.io/skills/dev`;
  only its current snapshot is retained.
- The stable portable installer is `npx --yes skills@latest`.
- Updates do not prune retired names automatically.
- Skills do not replace repository policy, review, secret scanning, or access
  control.
