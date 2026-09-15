# Agent Skills

[Русский](README.ru.md)

Portable Agent Skills for Codex and OpenCode, plus `skills-opencode`, a
first-class OpenCode integration. The two components are independent: use either
one on its own or install both for the complete OpenCode experience.

## Project Components

| Component                | What it provides                                                                          | Lifecycle                                                                                     |
| ------------------------ | ----------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Portable Agent Skills    | 29 self-contained workflows for engineering, documentation, delivery, and team operations | Installed with the stable `skills@latest` CLI into `~/.agents/skills` or `.agents/skills`     |
| `@kisev/skills-opencode` | OpenCode commands, fixed agents, routing tools, diagnostics, and optional plugin wrappers | Installed as an npm dependency; managed assets live under `~/.config/opencode` or `.opencode` |

Portable skills do not require the npm package. The npm package does not contain,
install, update, or remove portable skills.

## Portable Skills

Install the current stable portable distribution globally for Codex and
OpenCode:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --agent opencode --agent codex --skill '*' --copy --global --yes
```

The stable channel exposes current release metadata and digest-bound archives.
Start with the [guided installation](docs/tutorials/getting-started.md), use the
[portable skills how-to](docs/how-to/portable-skills.md) for project installs,
updates, cleanup, and troubleshooting, or browse the
[skill catalog](docs/reference/skill-catalog.md).

## skills-opencode

`@kisev/skills-opencode` extends OpenCode with:

- slash-command adapters for installed skills and package tools;
- six fixed agent roles and profile management;
- capability routing, installation, reconcile, and doctor tooling;
- opt-in `rules-injector`, `rtk`, and `zed-bell` plugin wrappers.

Install the package persistently in the npm project that owns the integration,
then preview its managed assets:

```shell
npm install --save-exact @kisev/skills-opencode
npx --yes @kisev/skills-opencode@latest install --scope project --dry-run
```

This only starts the mandatory flow. Apply the exact confirmation command from
the preview, add the package to the user-owned OpenCode `plugin` entry, and
restart OpenCode. Follow the complete
[OpenCode integration guide](docs/how-to/opencode-integration.md).

## Documentation

The [documentation index](docs/README.md) organizes tutorials, how-to guides,
reference material, and explanations using Diataxis. Architecture, verification,
migration, compatibility, and both installation lifecycles are linked there.

## Development

```shell
mise install
task check
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for source boundaries and focused checks.
Security reporting is in [SECURITY.md](SECURITY.md), release history in
[CHANGELOG.md](CHANGELOG.md), and licensing in [LICENSE](LICENSE).
