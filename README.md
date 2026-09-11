# Agent Skills

[Русский](README.ru.md)

Portable Agent Skills for Codex and OpenCode, plus an optional OpenCode-specific
npm integration.

## Two Independent Layers

| Layer                         | Global location                                   | Project location                                            |
| ----------------------------- | ------------------------------------------------- | ----------------------------------------------------------- |
| Portable skills               | `~/.agents/skills`                                | `.agents/skills`                                            |
| Optional OpenCode integration | npm project and assets under `~/.config/opencode` | package in project `node_modules`, assets under `.opencode` |

The layers have independent install, update, and removal lifecycles. Portable
skills contain the workflows and work without the npm package. The package adds
OpenCode commands, agents, tools, routing, and optional plugin wrappers; it does
not contain or install portable skills.

## Global Quick Start

Install the exact `v2.0.6` portable release for both hosts:

```shell
npx --yes skills@1.5.23 add https://github.com/kisev/skills/tree/v2.0.6 --agent opencode --agent codex --skill '*' --copy --global --yes
```

This creates one canonical copy in `~/.agents/skills` for both hosts.

## Codex and OpenCode

- Codex only: use `--agent codex`.
- OpenCode only: use `--agent opencode`.
- Both hosts: use `--agent opencode --agent codex`; `--copy` keeps one canonical
  copy for the selected scope.

Omit `--global` for a project installation. The canonical project copy is
`.agents/skills`:

```shell
npx --yes skills@1.5.23 add https://github.com/kisev/skills/tree/v2.0.6 --agent opencode --agent codex --skill '*' --copy --yes
```

For OpenCode, use this mandatory integration flow when the package is needed:
install it persistently in the owning npm project, run
`skills-opencode install --dry-run`, execute the exact confirmation command,
add the package to the user-owned `plugin` entry, and restart OpenCode. Only
then run reconcile. Install or upgrade the package before every reconcile. The
package must remain installed in project `node_modules` or in the npm project at
`~/.config/opencode`; follow the
[OpenCode integration guide](packages/opencode/README.md). Its installer neither
installs portable skills nor edits `opencode.json`.

The installer wizard preserves four independent groups: Skill command adapters,
Package command adapters, Fixed agents, and Selectable plugins. Adapter choices
select package command assets, not portable skills. Install portable skills only
with the pinned `npx --yes skills@1.5.23` command above.

## Pinned Release and Latest Source

The current immutable source is
`https://github.com/kisev/skills/tree/v2.0.6`. List its catalog without writing:

```shell
npx --yes skills@1.5.23 add https://github.com/kisev/skills/tree/v2.0.6 --list
```

Use `kisev/skills` separately when you intentionally want the latest source from
the repository rather than a pinned release:

```shell
npx --yes skills@1.5.23 add kisev/skills --agent opencode --agent codex --skill '*' --copy --global --yes
```

Install one skill by replacing `'*'` with its exact current name.

## Update

A tag installation remains pinned to that tag:

```shell
npx --yes skills@1.5.23 update --global --yes
```

Omit `--global` for project scope. To move to another release, repeat `add` with
the new exact tag URL. `update` refreshes tracked skills but does not prune names
renamed or deleted upstream.

Update the OpenCode integration independently: install the exact npm version in
its owning npm project, run a new `install --dry-run`, execute the exact
confirmation command from that preview, and restart OpenCode. See the
[package update flow](packages/opencode/README.md#update).

## Cleanup

The current migration inventory has exactly eight retired portable names:

| Retired                                    | Replacement                                                                                      |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| `attempt`, `schedule`, `usage`, `overview` | None                                                                                             |
| `project-spec`                             | `spec-manage`                                                                                    |
| `skill-improver`                           | `skill-improve`                                                                                  |
| `walkthrough`                              | `code-explain`                                                                                   |
| `team-workflow`                            | `team-sprint-start`, `team-sprint-close`, `team-retro`, `team-roadmap`, `slides-prompts-prepare` |

For a Codex-only global installation, remove the names explicitly:

```shell
npx --yes skills@1.5.23 remove attempt schedule usage overview project-spec skill-improver walkthrough team-workflow --agent codex --global --yes
```

For an OpenCode installation or a canonical copy shared by both hosts, either
remove them explicitly from the selected agents:

```shell
npx --yes skills@1.5.23 remove attempt schedule usage overview project-spec skill-improver walkthrough team-workflow --agent opencode --agent codex --global --yes
```

Do not use package install or reconcile to update or remove portable skills. Omit
`--global` for project scope. Avoid `remove --all` unless every portable skill in
that scope should be removed. Package reconcile has a separate lifecycle for
package-owned assets; conflicts, worktrees, and runtime state are preserved.
There is no archive restore or purge command.

## Doctor

List installed portable skills:

```shell
npx --yes skills@1.5.23 list --global
```

If a new skill is not visible, check `~/.agents/skills` or `.agents/skills` and
restart the host. After a tag change, repeat `add` for renamed additions and run
the explicit cleanup above for retired names.

Run the integration doctor through the npm project where the package is installed:

```shell
npm --prefix "$HOME/.config/opencode" exec -- skills-opencode doctor --scope global
npm --prefix "$HOME/.config/opencode" exec -- skills-opencode doctor --scope global --json
```

`doctor` is read-only. Exit status `0` is clean, `1` reports findings, and `2`
reports invalid input or an incomplete probe failure. Inspect conflicts instead
of overwriting them.

## Current Catalog

| Skill                    | Purpose                                                                                                    |
| ------------------------ | ---------------------------------------------------------------------------------------------------------- |
| `agents-md`              | Create or review repository-scoped `AGENTS.md` instructions.                                               |
| `askme`                  | Clarify an incomplete task or design through a bounded interview.                                          |
| `ast-grep`               | Run structural search or a confirmed AST rewrite through ast-grep.                                         |
| `code-explain`           | Build a read-only guided map of current WIP, a Git range, branch, or MR history.                           |
| `code-review`            | Review a GitLab MR or local WIP for defects and risks.                                                     |
| `commit-msg`             | Produce one concise English commit message from local changes.                                             |
| `docs-prepare`           | Prepare one evidence-based user document and private preview.                                              |
| `docs-review`            | Review user documentation for accuracy and usability.                                                      |
| `doit`                   | Implement an engineering task with preview, bounded writes, and checks.                                    |
| `goal`                   | Produce a read-only structured Markdown goal of at most 4000 characters.                                   |
| `humanize`               | Edit technical prose into direct, natural language.                                                        |
| `lsp-report`             | Report host-neutral LSP applicability, configuration, binary, and runtime states without starting servers. |
| `mattermost`             | Read and analyze a bounded Mattermost post, thread, channel, or chat.                                      |
| `mr-prepare`             | Prepare metadata and a local publication plan for a GitLab MR.                                             |
| `release-prepare`        | Prepare a release MR, inventory, announcement, and publication plan.                                       |
| `release-review`         | Review a release MR for completeness and compatibility.                                                    |
| `rtk`                    | Use RTK selectively to compress verbose command output.                                                    |
| `skill-improve`          | Check and improve one Agent Skill through an iterative loop.                                               |
| `slides-prompts-prepare` | Prepare prompts for team presentation slides from explicit context.                                        |
| `spec-manage`            | Initialize, onboard, update, or audit canonical project specifications.                                    |
| `stopit`                 | Write a sanitized handoff for the next session.                                                            |
| `summary`                | Turn transcripts, notes, or research into a structured factual summary.                                    |
| `task-prepare`           | Prepare a storage-neutral, self-contained work item without publication.                                   |
| `task-review`            | Review a storage-neutral work item without changing external state.                                        |
| `task-triage`            | Triage explicit storage-neutral work-item material read-only.                                              |
| `team-retro`             | Prepare one retrospective from explicit team context.                                                      |
| `team-roadmap`           | Prepare one roadmap view from explicit team context.                                                       |
| `team-sprint-close`      | Close one sprint cycle from explicit team context.                                                         |
| `team-sprint-start`      | Start one sprint cycle from explicit team context.                                                         |

The exact active and retired inventory is in the
[Migration Inventory](docs/migration-inventory.md).

## Development

Install the pinned toolchain and run the complete quality gate:

```shell
mise install
task check
```

Useful focused commands:

```shell
task eval:check
task generate:check
lefthook install
```

`task generate` materializes declared shared copies and creates ignored build
outputs. Change canonical sources in `shared/references/` or
`packages/opencode/src/registry.ts`, not generated copies. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the check structure.

## Reference and Limits

- Current portable release: `https://github.com/kisev/skills/tree/v2.0.6`.
- Latest source selector: `kisev/skills`.
- Portable installer: `npx --yes skills@1.5.23`.
- OpenCode integration: `@kisev/skills-opencode@2.0.6`, Node.js 22+, OpenCode
  `>=1.18.29 <1.19.0`.
- Portable runners use Python 3.12+ standard library only when a runner is needed.
- `ast-grep` and `rtk` require their external CLI; skills do not install them.
- Skills and integration assets do not replace repository policy, review, secret
  scanning, or access control.

Behavioral coverage is described in [Verification](docs/verification.md).
Security reporting is in [SECURITY.md](SECURITY.md), release history in
[CHANGELOG.md](CHANGELOG.md), and the license in [LICENSE](LICENSE).
