# memomatic

[Русская версия](README.ru.md)

`@kisev/memomatic` is a personal learning memory for agents following the OpenClaw
memory architecture: a tiered Markdown corpus you can read as plain files, a
rebuildable SQLite index with FTS5 and optional local embeddings, and a nightly
`dream` consolidation sweep.

## Install

```bash
npm install --global @kisev/memomatic
```

The corpus lives under `$XDG_STATE_HOME/memomatic/` (`MEMORY.md`, `USER.md`,
daily notes, `DREAMS.md`); rules live in `$XDG_CONFIG_HOME/memomatic/MEMORY_RULES.md`.
Requires Node.js 22+. Explicitly select `memomatic` in the `@kisev/agentomatic`
installer and restart OpenCode. For standalone use, run the CLI:

```bash
memomatic process    # validate the inbox and index accepted entries (no model)
memomatic dream      # full sweep: inbox + sessions + consolidation
```

The nightly sweep is scheduled by the systemd user units in `assets/systemd/`
(`memomatic-dream.service` and `memomatic-dream.timer`).

Configure `dream.model` and an OpenCode provider before expecting session
extraction; without a model, the session watermark is preserved. Follow the
[setup, first-entry, and scheduling guide](../../docs/how-to/memomatic.md).

## Inbox

All writes are asynchronous. Skills, agents, and the `memory_write` tool
append Markdown entry lines to `$XDG_STATE_HOME/memomatic/inbox/`:

```markdown
- Durable outcome in one sentence. <!-- source: team-retro --> <!-- key: stable-id -->
```

The next `process` or `dream` pass validates drops, applies `never-save`
rules, deduplicates exact texts, supersedes entries sharing a `key`, rebuilds
the SQLite index with batch embeddings, and moves rejected drops to
`inbox/rejected/`. Producers detect the inbox by presence and skip silently
when memomatic is absent.

Every entry can carry a `source` annotation. Visibility derives from it:
`team-*`, `gitlab`, and `spec-manage` entries may be quoted in team-facing
artifacts; every other source (`people-journal`, `stopit`,
`mattermost-triage`, `task-*`, `docs-*`, `user`) is personal-only. The label
is exposed in search responses and session bootstrap blocks.

## Surfaces

- `memomatic` CLI: `process`, `dream`, `search`, `status`, `index`.
- MCP stdio server with `memory_search`, `memory_get`, `memory_write`, and
  `memory_forget` tools.
- The OpenCode plugin re-exported by `@kisev/agentomatic`; its bootstrap
  injects curated memory plus project- and trigger-matched recall blocks
  resolved from the session database (`projects` map in `settings.json`).

Nothing is deleted without the explicit directives documented in
`MEMORY_RULES.md`.
