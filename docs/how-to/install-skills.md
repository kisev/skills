# Installing and Managing Skills

[Русский](../ru/how-to/install-skills.md)

`skillmate` is the single installer-configurator for this project's portable
skills, their command surfaces, and host configuration across Codex, Claude,
and OpenCode, in project and global scopes. It installs from the versioned
GitHub Pages distribution by default and never falls back to a guessed
source; a local checkout is a dev-only mode.

## Prerequisites

- Python 3.12+ with [`uv`](https://docs.astral.sh/uv/) (`uvx skillmate`) or
  `pip` (`pip install skillmate`).
- For the dev checkout mode: a local clone of this repository with
  [`mise`](https://mise.jdx.dev/) and [`task`](https://taskfile.dev) available.

## Install

Preview the plan, then apply it:

```shell
uvx skillmate install
uvx skillmate install --yes
```

Select hosts and scope explicitly when the defaults are not what you want:

```shell
uvx skillmate install --hosts claude,opencode --scope global --yes
uvx skillmate install --skill commit-msg --skill verification --yes
```

Placement follows each host's native directories:

| Host | Skills, project | Skills, global | Commands |
| - | - | - | - |
| Codex | `.agents/skills/` | `~/.agents/skills/` | none — skills are invoked as `$name` |
| Claude | `.claude/skills/` | `~/.claude/skills/` | `.claude/commands/*.md` |
| OpenCode | `.opencode/skills/` | `~/.config/opencode/skills/` | `.opencode/commands/*.md` |

Each host receives its own materialized copy: the canonical content with
only dialect transforms applied (Codex spells skill references `$name`).
Installing OpenCode together with Claude or Codex makes OpenCode see the same
skills through its compatible directories too; the plan states this
duplicate visibility because OpenCode documents no duplicate-name precedence.

Restart the host after installing or updating so new skills and commands are
discovered.

## Update and Pin Versions

Every installation records the distribution version it installed. `update`
previews the per-file delta and applies it after confirmation:

```shell
uvx skillmate update --yes
uvx skillmate update --version <version> --yes
```

## Remove

Removal uninstalls only files skillmate owns, per host and scope:

```shell
uvx skillmate remove --yes
uvx skillmate remove --hosts claude --scope global --yes
```

A file you modified after installation is reported as drifted and is removed
only with an explicit `--confirm-drift`.

## Diagnose

`doctor` reads the installations and names every problem with its repair:
missing files, version drift against the distribution, drifted files, stale
ownership records, and foreign files occupying distribution paths. It never
writes.

```shell
uvx skillmate doctor
uvx skillmate status
```

## Dev Checkout Mode

For unpublished or experimental content, install from a working tree of this
repository. The mode runs the checkout's own build (`task distribution:build`) and stamps the installation as dev:

```shell
uvx skillmate install --from-checkout /path/to/skills --yes
```

`--from-checkout` and `--version` are mutually exclusive; a dev installation
reports `source: checkout` in `status`.

## Safety Model

Every write path goes through one plan: a preview of all changes, explicit
confirmation, ownership manifests that detect collisions with files skillmate
does not own, and drift preservation. Files skillmate does not own are never
touched, and a file you modified after installation is never silently
overwritten.

## The `npx skills` Channel

The same Pages distribution serves the `skills` CLI
(`npx --yes skills@latest add https://kisev.github.io/skills`). It installs
portable skills into `.agents/skills` and is kept compatible; `skillmate`
adds per-host placement, command surfaces, and the preview-confirm safety
model. Prefer one channel per scope to avoid managing the same skill twice.
