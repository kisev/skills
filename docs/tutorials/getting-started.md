# Get Started with Portable Skills

[Русский](../ru/tutorials/getting-started.md)

This tutorial installs the current stable portable skill distribution for Codex
and OpenCode. It creates one canonical global copy that both hosts can use.

## Before You Start

You need Codex, OpenCode, or both, plus an environment where `npx` is available.
The command follows the stable installer channel and reads the supported GitHub Pages
distribution rather than the authored repository.

## 1. Install the Skills

Run:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --agent opencode --agent codex --skill '*' --copy --global --yes
```

This installs the current stable distribution into `~/.agents/skills`. `--copy`
keeps one canonical copy for both selected hosts. Release metadata and archive
digests identify the installed distribution.

If you use only one host, keep only its agent option:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --agent codex --skill '*' --copy --global --yes
```

or:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --agent opencode --skill '*' --copy --global --yes
```

## 2. Verify the Installation

List the installed global skills:

```shell
npx --yes skills@latest list --global
```

Restart the selected host if it was running during installation. The installed
skills should then be available from `~/.agents/skills`.

## 3. Decide Whether You Need skills-opencode

Portable skills already work in OpenCode. Install `@kisev/skills-opencode` only
if you also want OpenCode-specific commands, fixed agents, routing tools,
diagnostics, or optional plugin wrappers. The package has a separate lifecycle
and does not install portable skills.

Follow the [OpenCode integration guide](../how-to/opencode-integration.md) for
that optional layer. For project-scoped installation, updates, or cleanup, use
the [portable skills how-to](../how-to/portable-skills.md).
