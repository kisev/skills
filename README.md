# Agent Skills

[Русский](README.ru.md)

Portable Agent Skills for Codex and OpenCode, plus `agentomatic`, a
first-class OpenCode integration. The two components are independent: use either
one on its own or install both for the complete OpenCode experience.

## Project Components

| Component | What it provides | Lifecycle |
| - | - | - |
| Portable Agent Skills | 38 self-contained workflows for engineering, documentation, delivery, and team operations | Installed with the stable `skills@latest` CLI into `~/.agents/skills` or `.agents/skills` |
| `@kisev/agentomatic` | OpenCode commands, fixed agents, routing tools, diagnostics, and optional plugin wrappers | Installed as an npm dependency; managed assets live under `~/.config/opencode` or `.opencode` |

Portable skills do not require the npm package. The package does not contain,
install, update, inspect, or remove them. Their lifecycle is owned by the
`skills` CLI.

## Install Everything

The complete setup: portable skills, `agentomatic`, and the user-run
applications [memomatic](docs/how-to/memomatic.md) (agent memory) and
[taskmatic](docs/how-to/taskmatic.md) (local task board); rerun the same
commands to update. `install` and `config` ask for confirmation in a
terminal, or take explicit selection flags with `--yes` outside one. Until
a first stable release, `latest` is a prerelease. Restart OpenCode and
other running hosts, including MCP hosts and the taskmatic web service.

Everything on `latest`:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --global
npx --yes @kisev/agentomatic@latest install --global
npx --yes @kisev/agentomatic@latest config --global
npm install --global @kisev/memomatic
npm install --global @kisev/reviewmatic
npm install --global @kisev/taskmatic
```

Everything on `dev` (moves after every successful push to `dev`):

```shell
npx --yes skills@latest add https://kisev.github.io/skills/dev --global
npx --yes @kisev/agentomatic@dev install --global
npx --yes @kisev/agentomatic@dev config --global
npm install --global @kisev/memomatic@dev
npm install --global @kisev/reviewmatic@dev
npm install --global @kisev/taskmatic@dev
```

## Portable Skills

The default selection covers every host that reads `.agents/skills`,
including Codex and OpenCode, and the installer opens a picker with every
skill preselected; pass `--skill <name>` to choose explicitly. Start with the
[guided installation](docs/tutorials/getting-started.md), use the
[portable skills how-to](docs/how-to/portable-skills.md) for project installs,
updates, cleanup, and troubleshooting, or browse the
[skill catalog](docs/reference/skill-catalog.md).

## agentomatic

`@kisev/agentomatic` extends OpenCode with:

- slash-command adapters for installed skills;
- six fixed agent roles and profile management;
- capability routing plus direct CLI installation, diagnostics, profiles, and reconciliation;
- optional plugin wrappers: `rules-injector` and `zed-bell`, plus the `rtk`
  compression wrapper deployed by default and observable through `/rtk-stats`.

Global installs own the npm project at `~/.config/opencode` and create its
`package.json` when needed; for project scope, run the installer from the
project root without `--global`. The confirmed install also provisions the
persistent npm dependency that keeps the plugin resolvable. Restart OpenCode
after activation or asset changes, and follow the complete
[OpenCode integration guide](docs/how-to/opencode-integration.md).

## Documentation

The [documentation index](docs/README.md) organizes tutorials, how-to guides,
reference material, and explanations using Diataxis. The published
[documentation site](https://kisev.github.io/skills) shows the skill catalog,
interaction examples, and install instructions (`apps/docs-site`).

## Development

```shell
mise install
task install
task check
```

Further information:

- [CONTRIBUTING.md](CONTRIBUTING.md) - source boundaries and focused checks.
- [SECURITY.md](SECURITY.md) - vulnerability reporting.
- [CHANGELOG.md](CHANGELOG.md) - release history.
- [LICENSE](LICENSE) - license terms.
