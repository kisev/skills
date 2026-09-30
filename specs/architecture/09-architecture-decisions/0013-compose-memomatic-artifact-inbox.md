# ADR-0013: Compose memomatic with XDG skill artifacts through an async inbox

- Status: superseded
- Date: 2026-09-26
- Status changed: 2026-09-28
- Supersedes: none
- Superseded by: [ADR-0015](0015-use-explicit-mcp-memory.md)

The original decision below is retained as history. ADR-0015 preserves the inbox
and visibility contract but removes bootstrap recall and the host plugin.

## Context and problem statement

memomatic (ADR-0012) lives in its own XDG namespace while portable skills keep
state under `$XDG_STATE_HOME/agent-skills/` (people journal, stopit handoffs,
task-triage analyses, mattermost-triage digests) and author workspace artifacts
(specs, docs, retro reports). The two worlds never exchange knowledge: team and
project learnings never become personal memory, memory never reaches team
sessions, and stopit duplicates the "survive the session" mechanic with
different lifetime semantics.

## Decision drivers

- Keep portable skills self-contained: no runtime import of memomatic, no
  package dependency, graceful behavior on hosts without memomatic.
- One corpus writer: corpus invariants (atomic 0600 writes, history
  pre-images, rebuildable index) must stay inside memomatic.
- Asynchronous writes: producers drop Markdown, a scheduled or manual pass
  validates and indexes (batch embeddings), so saving never blocks a session.
- Store everything locally; separate data at usage time through provenance,
  not at write time through filters.
- SQLite brute-force vector search stays: the corpus is deliberately bounded
  (promotion gates, line budgets, archival); a vector daemon is not justified
  at the current scale.

## Considered options

- Dream sweep scans `agent-skills/` state directories directly (pull
  connectors per producer format).
- Skills call a `memomatic record` CLI contract with graceful degradation.
- Producers append Markdown entry lines into a memomatic inbox directory; a
  deterministic pass processes them (chosen).
- Qdrant as an optional or sole vector store (deferred).

## Outcome

Producers write single-format Markdown entry lines into
`$XDG_STATE_HOME/memomatic/inbox/`:

- scripted skills mirror their durable events through the shared
  `memomatic_inbox.py` helper (people journal entries with
  `people-<profile>-<id>` keys, stopit handoff distillates keyed per
  workspace, task-triage per-issue decisions keyed per issue, task-prepare
  outcomes);
- agent flows (docs, spec-manage ADRs, team retros and reports,
  mattermost-triage digests) invoke the same helper CLI after explicit
  confirmation, which eliminates malformed files;
- the `memory_write` tool and MCP server queue inbox drops instead of
  touching corpus files and answer with a flush hint.

`memomatic process` (new CLI command) is a deterministic, model-free pass:
validate lines, enforce `never-save`, deduplicate exact texts, supersede by
key, route user-origin targets, rebuild the index with embeddings, and move
rejected drops to `inbox/rejected/`. The nightly dream sweep runs the same
inbox pass first. A stale-tolerant run lock serializes dream and process
against each other. Inbox processing happens only via the systemd timer or a
manual CLI run; the plugin never processes.

Entry lines carry a `source` annotation. Visibility is derived from it:
`team-*`, `gitlab`, and `spec-manage` entries may be quoted in team-facing
artifacts; every other source (people-journal, stopit, mattermost-triage,
task-*, docs-*, user, sessions) is personal-only. Search responses and
bootstrap blocks expose the label, and team workflows forbid quoting
personal-only entries into team artifacts. `MEMORY_RULES.md` auto-clean
directives gain a `source=` filter so stopit distillates expire (transient
semantics) while durable memory persists.

The OpenCode plugin bootstrap now resolves session facts (directory, title,
first user message) from the OpenCode database and appends two bounded recall
blocks: project-matched episodic entries (`settings.json` `projects` map,
longest-prefix match) and trigger-phrase matches, both labeled with source
visibility. `experimental.chat.system.transform` receives only a session ID,
so the database is the session-context source.

## Consequences

### Positive

- One ingest contract replaces per-producer parsers; format changes stay
  inside the producing skill.
- Provenance travels with every entry, enabling usage-level visibility without
  write-time filtering.
- Single-writer corpus with an explicit lock; saves are fire-and-forget.
- Skills degrade silently when memomatic is absent (presence detection).

### Negative

- Saved entries are searchable only after the next process/dream run; the
  `memory_write` response carries the manual flush command.
- No retroactive import: memory starts from new events only.
- The helper must be materialized into every dropping skill archive.

### Qdrant migration trigger

Revisit a dedicated vector store only when the corpus exceeds roughly 20,000
entries or search latency exceeds roughly 50 ms; until then SQLite with
SQL-side source/project/visibility filtering is sufficient.

- Requirements: [REQ-I-407](../../capabilities/applications/memomatic.md#req-i-407---compose-skill-artifacts-into-memory-through-the-inbox)
