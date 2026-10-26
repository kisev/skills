# Agent Skills

[Русский](README.ru.md)

Portable Agent Skills for Codex, Claude, and OpenCode, with `skillmate` as the single installer-configurator.

## Project Components

| Component | What it provides | Lifecycle |
| - | - | - |
| Portable Agent Skills | 44 self-contained workflows for engineering, documentation, delivery, and team operations | Installed with `skillmate` or the stable `skills@latest` CLI into the host's skill directory |
| `skillmate` | One command to install skills, lay out command surfaces, and configure Codex, Claude, and OpenCode in project or global scope | Delivered on PyPI: `uvx skillmate` or `pip install skillmate` |

The `skills` CLI (the `npx skills` channel) installs portable skills from the same Pages distribution; `skillmate` adds host placement with per-host dialects, command surfaces, and the preview-confirm safety model.

## Install Everything

Install portable skills, `skillmate`, [memomatic](docs/how-to/memomatic.md), [reviewmatic](apps/reviewmatic/README.md), and [taskmatic](docs/how-to/taskmatic.md); rerun the commands to update. Reviewmatic runs from the repository through `uvx`, not npm or PyPI.
`skillmate install` previews the complete plan and writes only after confirmation (`--yes` skips the prompt). Restart the hosts after updates.

Skills through `skillmate` on the stable channel:

```shell
# Distribution version
uvx skillmate status

# Install into the project for all three hosts
uvx skillmate install --yes

# Or globally, or for selected hosts and skills
uvx skillmate install --scope global --hosts claude,opencode --yes
uvx skillmate doctor
```

Skills through the `skills` CLI (same distribution, compatible channel):

```shell
npm view --prefer-online skills@latest version
npx --yes skills@latest add https://kisev.github.io/skills --global
npx --yes skills@latest update --global
npx --yes skills@latest list --global
```

Reviewmatic from the exact release ref:

```shell
REVIEWMATIC_REF='<ref>' # use the exact release tag for the stable skills channel
uvx --from "git+https://github.com/kisev/skills.git@${REVIEWMATIC_REF}#subdirectory=apps/reviewmatic" reviewmatic --version
```

On the dev channel, install from a checkout of this repository — no registry is involved:

```shell
skillmate install --from-checkout /path/to/skills --yes   # unpublished working-tree content
REVIEWMATIC_REF=dev # moving development branch, matching the dev skills channel
uvx --refresh-package reviewmatic --from "git+https://github.com/kisev/skills.git@${REVIEWMATIC_REF}#subdirectory=apps/reviewmatic" reviewmatic --version
```

`skillmate status` reports installed versions per host and scope; `--version`
pins an exact distribution version. `uvx` runs reviewmatic ephemerally from
the selected Git ref and does not install a global tool. `--version` prints
the aligned release version: on an exact release tag it matches the tag, while
on the moving `dev` branch it stays at the last released version between
releases. `reviewmatic runtime-info` additionally reports the resolved Git
commit of the installed source. `skills list` inspects installed skills.

## Check the Environment Contract

Some skills need external tools: `git`, `glab`, `uv`/`uvx`, or an npm
application (for example `code-review`, `mr-prepare`, or `taskmatic`). Every
archive with such a dependency carries a materialized
`references/requirements.json` that lists each tool with its check command, a
copy-ready install command, and the distribution `source_revision`. Run the
bundled stdlib check in the first session and show its output; it installs
nothing and makes no network call:

```shell
python3 ~/.agents/skills/code-review/scripts/check_environment.py
```

Each line is `OK` or `FAIL`, and every failure prints the exact repair command.
`skillmate doctor` reads the same manifests for the global and project scopes
and reports missing files, version drift, foreign files, and repair commands.

## Guides

- [Installing and managing skills](docs/how-to/install-skills.md): hosts, scopes, command surfaces, updates, removal, and the dev checkout mode. See the [tutorial](docs/tutorials/getting-started.md) and [catalog](docs/reference/skill-catalog.md).
- [Portable skills](docs/how-to/portable-skills.md): project installs, updates, cleanup, and troubleshooting with the `skills` CLI. All `.agents/skills` hosts are selected by default; the picker preselects all skills. Use `--skill <name>` to limit selection. Upgrade a global installation interactively with `npx --yes skills@latest update --global` so retired names are offered for removal.
- [Documentation index](docs/README.md): Diataxis tutorials, how-to, reference, and explanation. The [site](https://kisev.github.io/skills) adds skill interaction examples and install instructions (`apps/docs-site`).

## Development

The shared [development environment](dev/README.md) runs GitLab and Mattermost.
Optional real-server checks: [GitLab](tests/integration/gitlab/README.md) and
[Mattermost](tests/integration/mattermost/README.md). Neither is required by `task check`.

```shell
mise install
task install
task check
```

[Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [Changelog](CHANGELOG.md) · [License](LICENSE).
