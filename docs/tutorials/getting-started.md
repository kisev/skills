# Get Started with Portable Skills

[Русский](../ru/tutorials/getting-started.md)

This tutorial installs the current stable portable skill distribution for every
host that reads `.agents/skills`, such as Codex and OpenCode. It creates one
canonical global copy shared by all of them.

## Before You Start

You need at least one host that reads `.agents/skills`, such as Codex or
OpenCode, plus an environment where `npx` is available.
The command follows the stable installer channel and reads the supported GitHub Pages
distribution rather than the authored repository.

## 1. Install the Skills

Run:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --global
```

The installer opens a skill picker with every skill preselected; deselect what
you do not need. Inside an agent session the command runs non-interactively and
installs everything, so pass `--skill <name>` there to stay selective. Skills
land in `~/.agents/skills` for every host that reads it, plus any other
installed host. Release metadata and archive digests identify the installed
distribution.

To install for one host only, restrict the selection with `--agent`:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --agent codex --global
```

or:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --agent opencode --global
```

## 2. Verify the Installation

List the installed global skills:

```shell
npx --yes skills@latest list --global
```

Restart your host if it was running during installation. The installed
skills should then be available from `~/.agents/skills`.

## 3. Decide Whether You Need agentomatic

Portable skills already work in OpenCode. Install `@kisev/agentomatic` only
if you also want OpenCode-specific commands, fixed agents, routing tools,
diagnostics, or optional plugin wrappers. The package has a separate lifecycle
and does not install portable skills.

Follow the [OpenCode integration guide](../how-to/opencode-integration.md) for
that optional layer. For project-scoped installation, updates, or cleanup, use
the [portable skills how-to](../how-to/portable-skills.md).
