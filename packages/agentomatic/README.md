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
  fragments into OpenCode `opencode.json(c)`/`cli.json`, `kilo.json(c)`, and
  `mimocode.json(c)` while preserving existing entries and comments.
- Optional plugin wrappers: `rules-injector` and `zed-bell`;
  the `rtk` compression wrapper is deployed by
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

- State: `$XDG_STATE_HOME/memomatic/` (corpus, index, history, archive) and
  `$XDG_STATE_HOME/memomatic/inbox/` where skills and agents queue asynchronous
  Markdown drops.
- Config: `$XDG_CONFIG_HOME/memomatic/settings.json` (embedding endpoint, dream
  model and variant, thresholds) and
  `MEMORY_RULES.md` with manual directives: `- never-save: <topic>` and opt-in
  `- auto-clean: older-than=90d scope=episodic [source=name]`.
- Tools: `memory_search`, `memory_get`, `memory_write`, `memory_forget`, exposed
  by the independently installed MCP stdio server (`memomatic mcp-serve`).
  The CLI provides `process`, `search`, `status`, `index`, and `dream --dry-run`.
  `memory_write` queues an inbox drop and answers with a flush hint; entries
  carry a `source` annotation whose derived visibility (`team-*`, `gitlab`,
  `spec-manage` are quotable in team artifacts, the rest personal-only) is
  exposed in search results. The model initiates retrieval through tool calls;
  there is no automatic memory injection or memomatic plugin.
- Scheduling: copy `memomatic-sessions.service`, `memomatic-sessions.timer`,
  `memomatic-dream.service`, and `memomatic-dream.timer` from the
  `@kisev/memomatic` package `assets/systemd/` into `~/.config/systemd/user/` and run
  `systemctl --user enable --now memomatic-sessions.timer memomatic-dream.timer`;
  run the sweeps another way by invoking `memomatic process`, `memomatic sessions`,
  or `memomatic dream` yourself.
- Forgetting is explicit or rule-gated: nothing is deleted without
  `memory_forget` or an `auto-clean` directive; pinned entries never decay.

Agentomatic does not depend on memomatic. See the [MCP setup and legacy plugin
migration guide](../../docs/how-to/memomatic.md).

## Requirements

- Node.js 22 or later.
- OpenCode `>=2.0.0 <2.1.0`. V1 users retain the last `11.0.x`
  [release](https://github.com/kisev/skills/releases), not `dev`.
- A persistent npm project that owns the dependency.

## Project Install

Run the installer from the repository root (add `--global` for the global
scope); the confirmed install also provisions the persistent npm dependency:

```shell
# Registry version
npm view --prefer-online @kisev/agentomatic@latest version

# Preview, then confirm the install
npx --yes @kisev/agentomatic@latest install --dry-run
npx --yes @kisev/agentomatic@latest install

# Installed dependency in the owning npm project
npm list @kisev/agentomatic --depth=0
```

Use `@kisev/agentomatic@dev` in both view and npx commands for the development
snapshot. Tags can move between preview and installation. npx does not install
a global CLI, and a dry run does not provision the dependency. For a confirmed
global install, check `npm list --prefix "$HOME/.config/opencode" @kisev/agentomatic --depth=0`.

The confirmed install pins the executing version into the nearest npm project;
global installs own `~/.config/opencode` and create its `package.json` when
needed. Offline setups can provision the dependency by hand first:
`npm install --save-exact @kisev/agentomatic`, then run
`npx agentomatic install --dry-run` from that project so the executing version
matches the installed package. Confirm the printed plan summary in the install
step, or pass explicit selections with `--yes` outside a terminal.
When core integration is selected, the same confirmed install
merges the `plugins` entry into user-owned OpenCode configuration while preserving
existing entries. The separate `config` command can apply additional fragments
or retry a failed configuration step:

```shell
npx agentomatic config --global --dry-run
```

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugins": ["@kisev/agentomatic"]
}
```

Restart OpenCode after activation or asset changes. A confirmed `install` can
apply its core config step; `uninstall` never edits user configuration. Other
fragments use `config`, and command adapter selections do not install portable
skills. OpenCode config output uses native V2 `plugins` and `permissions`;
only touched legacy sections migrate, with ambiguous cases reported as conflicts.

## Documentation

The canonical documentation lives in `docs/`, not in the package source:

- [Complete OpenCode integration guide](https://github.com/kisev/skills/blob/main/docs/how-to/opencode-integration.md)
- [Portable skills guide](https://github.com/kisev/skills/blob/main/docs/how-to/portable-skills.md)
- [Documentation index](https://github.com/kisev/skills/blob/main/docs/README.md)

The complete guide covers global installation, asset selection, confirmation,
activation, `config` fragments, `doctor`, update, `reconcile`, agent profiles,
ownership, and uninstall.
