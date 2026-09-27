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

## Portable Skills

Install the current stable portable distribution globally. The default agent
selection covers every host that reads `.agents/skills`, including Codex and
OpenCode:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --global
```

The installer opens a skill picker with every skill preselected; deselect what
you do not need, or pass `--skill <name>` to choose explicitly.

The stable channel exposes current release metadata and digest-bound archives.
To opt into the moving development channel instead, install from
`https://kisev.github.io/skills/dev`; it updates after successful pushes to
`dev` and does not change the stable installation source.
Start with the [guided installation](docs/tutorials/getting-started.md), use the
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

Run the installer from any directory; the confirmed install also provisions the
persistent npm dependency that keeps the plugin resolvable:

```shell
npx --yes @kisev/agentomatic@latest install --global --dry-run
```

For project scope, run it from the project root without `--global`. Global
installs own the npm project at `~/.config/opencode` and create its
`package.json` when needed; project installs use the nearest npm project. Use
`@kisev/agentomatic@dev` to opt into the development snapshot, or install the
package once with `npm install -g @kisev/agentomatic` to call the `agentomatic`
binary directly.

This only starts the mandatory flow. Rerun the install command without
`--dry-run` and answer the confirmation question for the printed plan summary,
or add `--yes` outside a terminal. Then add the package to the user-owned
OpenCode `plugin` entry and restart OpenCode. Follow the complete
[OpenCode integration guide](docs/how-to/opencode-integration.md).

## Documentation

The [documentation index](docs/README.md) organizes tutorials, how-to guides,
reference material, and explanations using Diataxis. Architecture, verification,
migration, compatibility, and both installation lifecycles are linked there.

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
