# Agent Skills

[Русский](README.ru.md)

Portable Agent Skills for Codex and OpenCode, plus the independent `agentomatic` OpenCode integration. Use either component on its own or both together.

## Project Components

| Component | What it provides | Lifecycle |
| - | - | - |
| Portable Agent Skills | 40 self-contained workflows for engineering, documentation, delivery, and team operations | Installed with the stable `skills@latest` CLI into `~/.agents/skills` or `.agents/skills` |
| `@kisev/agentomatic` | OpenCode commands, fixed agents, routing tools, diagnostics, and optional plugin wrappers | Installed as an npm dependency; managed assets live under `~/.config/opencode` or `.opencode` |

The `skills` CLI owns portable skills; the npm integration does not contain, install, update, inspect, or remove them.

## Install Everything

Install portable skills, `agentomatic`, [memomatic](docs/how-to/memomatic.md), [reviewmatic](apps/reviewmatic/README.md), and [taskmatic](docs/how-to/taskmatic.md); rerun the commands to update. The `update` pass after `add` also offers to remove retired skill names.
`install` and `configure` require terminal confirmation or explicit selections with `--yes`. Before a package's first stable release, `latest` can be a prerelease.
Restart OpenCode, other running MCP hosts, and the taskmatic web service after updates.

Everything on `latest`:

```shell
# Registry versions
npm view --prefer-online skills@latest version
npm view --prefer-online @kisev/agentomatic@latest version
npm view --prefer-online @kisev/memomatic@latest version
npm view --prefer-online @kisev/reviewmatic@latest version
npm view --prefer-online @kisev/taskmatic@latest version

# Install and configure
npx --yes skills@latest add https://kisev.github.io/skills --global
npx --yes skills@latest update --global
npx --yes @kisev/agentomatic@latest install --global
npx --yes @kisev/agentomatic@latest configure integration --global
npm install --global @kisev/memomatic
npm install --global @kisev/reviewmatic
npm install --global @kisev/taskmatic

# Local installation and active CLIs
npm list --prefix "$HOME/.config/opencode" @kisev/agentomatic --depth=0
npm list --global @kisev/memomatic @kisev/reviewmatic @kisev/taskmatic --depth=0
memomatic --version
reviewmatic --version
taskmatic --version
npx --yes skills@latest list --global
```

Everything on `dev` (moves after every successful push to `dev`):

```shell
# Registry versions
npm view --prefer-online skills@latest version
npm view --prefer-online @kisev/agentomatic@dev version
npm view --prefer-online @kisev/memomatic@dev version
npm view --prefer-online @kisev/reviewmatic@dev version
npm view --prefer-online @kisev/taskmatic@dev version

# Install and configure
npx --yes skills@latest add https://kisev.github.io/skills/dev --global
npx --yes skills@latest update --global
npx --yes @kisev/agentomatic@dev install --global
npx --yes @kisev/agentomatic@dev configure integration --global
npm install --global @kisev/memomatic@dev
npm install --global @kisev/reviewmatic@dev
npm install --global @kisev/taskmatic@dev

# Local installation and active CLIs
npm list --prefix "$HOME/.config/opencode" @kisev/agentomatic --depth=0
npm list --global @kisev/memomatic @kisev/reviewmatic @kisev/taskmatic --depth=0
memomatic --version
reviewmatic --version
taskmatic --version
npx --yes skills@latest list --global
```

Tags can move between preview and installation. `npm list` checks installed
packages; `--version` checks the CLI on PATH. npx does not install a global CLI;
`skills list` inspects installed skills, not the npm installer version.

## Guides

- [Portable skills](docs/how-to/portable-skills.md): project installs, updates, cleanup, and troubleshooting. All `.agents/skills` hosts are selected by default; the picker preselects all skills. Use `--skill <name>` to limit selection. Upgrade a global installation interactively with `npx --yes skills@latest update --global` so retired names are offered for removal. See the [tutorial](docs/tutorials/getting-started.md) and [catalog](docs/reference/skill-catalog.md).
- [OpenCode integration](docs/how-to/opencode-integration.md): command adapters, six agent roles, routing, diagnostics, profiles, reconciliation, optional `rules-injector`/`zed-bell`, and default `rtk` with `/rtk-stats`.
  Confirmed global installs provision the dependency in `~/.config/opencode`, creating `package.json` if needed; for project scope, run from the project root without `--global`. Restart OpenCode after activation or asset changes.
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
