# memomatic

[Русская версия](README.ru.md)

`@kisev/memomatic` is a personal learning memory for agents following the OpenClaw
memory architecture: a tiered Markdown corpus you can read as plain files, a
rebuildable SQLite index with FTS5 and optional local embeddings, a `sessions`
extraction pass, and a nightly `dream` consolidation sweep.

## Install

```bash
npm install --global @kisev/memomatic
```

The corpus lives under `$XDG_STATE_HOME/memomatic/` (`MEMORY.md`, `USER.md`,
daily notes, `DREAMS.md`); rules live in `$XDG_CONFIG_HOME/memomatic/MEMORY_RULES.md`.
Requires Node.js 22.13+. Connect `memomatic mcp-serve` as a local stdio MCP server
in OpenCode, Kilo, MiMo, or another MCP host and restart that host. No plugin or
automatic context injection is used. For background processing, run the CLI:

```bash
memomatic process    # validate the inbox and index accepted entries (no model)
memomatic sessions   # extract episodic memory from OpenCode sessions (model)
memomatic dream      # consolidation: inbox + promotion + bounded rewrite + archive
```

Nightly runs are scheduled by the systemd user units in `assets/systemd/`
(`memomatic-sessions.service`/`.timer` for extraction and
`memomatic-dream.service`/`.timer` for consolidation).

Configure `sessions.model` (or keep a legacy `dream.model`) and an OpenCode
V2 provider before expecting session extraction; without a model, the session
watermark is preserved. Session extraction and its model server require
OpenCode `2.x`; a pre-V2 session database is not parsed. Follow the
[setup, first-entry, and scheduling guide](../../docs/how-to/memomatic.md).

## CLI, Sessions, and Dream

See [CLI conventions](../../docs/reference/cli.md) and
[Dream controls](../../docs/how-to/memomatic.md#observe-limit-and-resume-dream).
`sessions --plan` inspects pending session work without a model; `dream --plan`
counts pending inbox files and promotion candidates. `--dry-run` previews
either command and may still call models. Sessions drain the eligible snapshot
with per-fragment checkpoints, reusing one OpenCode server and unchanged
embeddings; Dream then promotes usage-gated episodic entries into `MEMORY.md`
through bounded consolidation and archives old entries. The first
legacy-cursor migration checks prior history once without discarding existing
memory. `status` shows the queue: pending inbox files, session backlog,
promotion candidates, and the last run of each sweep.

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
is exposed in search responses.

## Surfaces

- `memomatic` CLI: `process`, `sessions`, `dream`, `search`, `status`, `index`.
- MCP stdio server with `memory_search`, `memory_get`, `memory_write`, and
  `memory_forget` tools.

The model initiates memory searches through visible MCP tool calls. The
`sessions` command processes OpenCode history separately; connecting another
host does not import its session history. Agentomatic and memomatic are
installed independently.

Nothing is deleted without the explicit directives documented in
`MEMORY_RULES.md`.
