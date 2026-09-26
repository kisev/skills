# OpenCode Integration

[Русский](README.ru.md)

`@kisev/agentomatic` is the first-class OpenCode-specific component of
Agent Skills. It complements the portable skills but has its own installation,
update, and removal lifecycle.

## What It Adds

- OpenCode slash-command adapters for installed portable skills.
- Six fixed agents: `manager`, `architect`, `mapper`, `worker`, `review`, and
  `critic`.
- Capability routing plus direct CLI diagnostics, reconciliation, and profiles.
- A confirmed `config` command that connects the package and recommended
  fragments into `opencode.json(c)`, `tui.json`, `kilo.json(c)`, and
  `mimocode.json(c)` while preserving existing entries and comments.
- Optional plugin wrappers: `rules-injector`, `zed-bell`, and `memomatic`
  personal learning memory; the `rtk` compression wrapper is deployed by
  default and observable through `/rtk-stats` and `doctor`.

The package does not contain, install, update, inspect, or remove portable skills.
Their lifecycle is owned by the `skills` CLI.

## Memomatic

Memomatic is personal learning memory inspired by the OpenClaw architecture:
tiered Markdown (`MEMORY.md`, `USER.md`, daily notes, `DREAMS.md`), a rebuildable
SQLite index with FTS5 keyword search and optional local embeddings, and a
nightly dream sweep that ingests session transcripts, promotes repeatedly useful
entries through deterministic gates and one bounded model turn, supersedes
outdated facts by key, and archives every pre-image.

- State: `$XDG_STATE_HOME/memomatic/` (corpus, index, history, archive).
- Config: `$XDG_CONFIG_HOME/memomatic/settings.json` (embedding endpoint, dream
  model and variant, thresholds) and `MEMORY_RULES.md` with manual directives:
  `- never-save: <topic>` and opt-in `- auto-clean: older-than=90d scope=episodic`.
- Tools: `memory_search`, `memory_get`, `memory_write`, `memory_forget`, exposed
  by the plugin, by the MCP stdio server (`agentomatic-memomatic mcp-serve`),
  and by the CLI (`search`, `status`, `index`, `dream --dry-run`).
- Scheduling: copy `memomatic-dream.service` and `memomatic-dream.timer` from the
  package `assets/systemd/` into `~/.config/systemd/user/` and run
  `systemctl --user enable --now memomatic-dream.timer`; run the sweep another
  way by invoking `agentomatic-memomatic dream` yourself.
- Forgetting is explicit or rule-gated: nothing is deleted without
  `memory_forget` or an `auto-clean` directive; pinned entries never decay.

## Requirements

- Node.js 22 or later.
- OpenCode `>=1.18.29 <1.19.0`.
- A persistent npm project that owns the dependency.

## Project Install

Install the package in the repository's npm project and preview the managed
assets:

```shell
npm install --save-exact @kisev/agentomatic
npx --yes @kisev/agentomatic@latest install --dry-run
```

Run the exact confirmation command printed by the preview. If the selected
assets need core integration, connect the package into the user-owned OpenCode
configuration yourself or through the confirmed `config` command, which merges
the `plugin` entry while preserving existing entries:

```shell
npx --yes @kisev/agentomatic@latest config --global --dry-run
```

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@kisev/agentomatic"]
}
```

Restart OpenCode after activation or asset changes. The `install` and
`uninstall` commands never edit `opencode.json`; `config` is the only confirmed
path for configuration fragments, and command adapter selections do not install
portable skills.

## Documentation

The canonical documentation lives in `docs/`, not in the package source:

- [Complete OpenCode integration guide](https://github.com/kisev/skills/blob/main/docs/how-to/opencode-integration.md)
- [Portable skills guide](https://github.com/kisev/skills/blob/main/docs/how-to/portable-skills.md)
- [Documentation index](https://github.com/kisev/skills/blob/main/docs/README.md)

The complete guide covers global installation, asset selection, confirmation,
activation, `config` fragments, `doctor`, update, `reconcile`, agent profiles,
ownership, and uninstall.
