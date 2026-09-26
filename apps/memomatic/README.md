# memomatic

[Русская версия](README.ru.md)

`@kisev/memomatic` is a personal learning memory for agents following the OpenClaw
memory architecture: a tiered Markdown corpus you can read as plain files, a
rebuildable SQLite index with FTS5 and optional local embeddings, and a nightly
`dream` consolidation sweep.

## Install

```bash
npm install @kisev/memomatic
```

The corpus lives under `$XDG_STATE_HOME/memomatic/` (`MEMORY.md`, `USER.md`,
daily notes, `DREAMS.md`); rules live in `$XDG_CONFIG_HOME/memomatic/MEMORY_RULES.md`.
The `@kisev/agentomatic` installer deploys the OpenCode plugin automatically;
standalone use runs the CLI:

```bash
memomatic dream --dry-run
```

The nightly sweep is scheduled by the systemd user units in `assets/systemd/`
(`memomatic-dream.service` and `memomatic-dream.timer`).

## Surfaces

- `memomatic` CLI: corpus inspection and the `dream` sweep.
- MCP stdio server with `memory_search`, `memory_get`, `memory_write`, and
  `memory_forget` tools.
- The OpenCode plugin re-exported by `@kisev/agentomatic`.

Nothing is deleted without the explicit directives documented in
`MEMORY_RULES.md`.
