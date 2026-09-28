---
review: {"components": ["memomatic"], "sources": ["apps/memomatic/src/*", "apps/memomatic/test/*", "packages/agentomatic/src/plugins/memomatic.ts", "packages/agentomatic/test/memomatic-plugin.test.mjs"], "contracts": ["specs/architecture/08-crosscutting-concepts/security-trust-mutations.md"]}
---

# Plugin `memomatic`

## Purpose

Provide optional personal learning memory: selective capture, hybrid search, gated background consolidation, and rule-gated forgetting, with OpenCode plugin tools, an MCP stdio server, and a scheduled dream CLI sharing one data model. Compose durable outcomes from portable skill artifacts into memory through an asynchronous inbox.

## Triggers and Near-Misses

Used when durable engineering outcomes should survive sessions; near-miss: storing full transcripts or file scans, which memomatic never does.

## Inputs/Outputs

Input is an OpenCode session, an explicit tool call, an inbox drop from a skill or agent, or the scheduled sweep; output is annotated Markdown entries under `$XDG_STATE_HOME/memomatic/` (`MEMORY.md`, `USER.md`, `memory/YYYY-MM-DD.md`, `DREAMS.md`), a rebuildable SQLite index, and tool responses. Producers append Markdown entry lines to `$XDG_STATE_HOME/memomatic/inbox/` (`<source>-<stamp>-<token>.md`, mode 0600); rejected drops move to `inbox/rejected/`.

## Workflow Stages

Capture (explicit `memory_write` queuing an inbox drop, skill mirrors through the shared `memomatic_inbox.py` helper, or dream ingestion of session transcripts from the OpenCode database), process (`memomatic process`: validate lines, enforce `never-save`, deduplicate exact texts, supersede by `key`, route user-origin `target` entries, rebuild the index with embeddings — no model turns), rank (hybrid FTS5 and optional local embeddings, recency decay with half-life 30 days for episodic entries, importance multiplier, pinned and curated entries exempt), account usage (surfaced on search hits, useful on line fetches), gate promotion deterministically (relevance 0.30, frequency 0.24, diversity 0.15, recency 0.15, consolidation 0.10, richness 0.06), consolidate through one bounded model turn via `opencode run` (merge, supersede by key, bounded prior-entry loss 0.25, line budget), and report to `DREAMS.md` with content-addressed pre-images in `history/`. Dream and process serialize through a stale-tolerant run lock; inbox processing runs only on the systemd timer or a manual CLI run.

Every entry carries a `source` annotation; visibility derives from it: `team-*`, `gitlab`, and `spec-manage` entries may be quoted in team-facing artifacts, every other source is personal-only. Search responses and the plugin bootstrap expose the label. The plugin bootstrap injects the curated `MEMORY.md` and `USER.md` heads plus two bounded recall blocks resolved from the OpenCode session database (directory, title, first user message): project-matched episodic entries through the `settings.json` `projects` longest-prefix map, and trigger-phrase matches.

## Dependencies

OpenCode plugin API tools and `experimental.chat.system.transform`, `node:sqlite`, optional OpenAI-compatible local embedding endpoint, configured OpenCode provider for dream model turns, presence-detected `$XDG_STATE_HOME/memomatic/inbox/` for skill producers.

Session ingestion and bootstrap read text parts from OpenCode's normalized `part`
table, ordered within each message; legacy databases with embedded message parts
remain readable. Dream invokes `opencode run --format json` with a positional
prompt and parses only text events, excluding tool and step metadata. Internal
Dream sessions remain excluded from extraction.

## Remote/Local Effects

No independent remote effect; dream model turns use the configured OpenCode provider and carry a `[memomatic-internal]` marker so ingestion never re-extracts them. Deletion is explicit (`memory_forget`) or enabled only by a `- auto-clean: older-than=Nd scope=episodic [source=name]` directive in `$XDG_CONFIG_HOME/memomatic/MEMORY_RULES.md`; `- never-save: <topic>` topics are rejected at write time, at inbox processing, and at dream extraction.

## Errors/Partial/Escalation

Invalid consolidation falls back to append-only within the line budget; unreadable session databases produce an empty ingestion window; bootstrap context injection never breaks a session; `dry-run` reports without writes; malformed or forbidden inbox drops move to `rejected/` and are reported in the dream summary; a busy run lock fails with `another memomatic run is active`.

Dry-run uses an in-memory index and leaves the corpus, persistent index, run lock,
and session watermark unchanged; configured model and embedding calls may still
run. Without a model, session extraction is skipped without advancing its
watermark. Consolidation cannot authorize a curated `drop`; auto-clean selects
individual matching unpinned old entries rather than removing a whole daily file.

## Unique Constraints

Curated files are written only by dream consolidation, explicit user-origin writes, or inbox routing of user-origin targets; superseded entries are excluded from search and indexing; usage counters are keyed by stable entry identity (`key` annotation or content digest); state roots are absolute, normalized, symlink-free, with atomic mode-0600 writes; `memory_write` never touches corpus files directly.

## Requirement

### REQ-I-406 - Expose memomatic safely

The package shall expose `memomatic` as a selectable plugin whose forgetting is explicit or rule-gated and whose consolidation stays inside deterministic bounds.

#### Verification

Memory regression tests reject traversal, sibling-prefix and symlink paths,
verify non-mutating dry-runs, retain unrelated entries during scoped cleanup,
and preserve curated entries on model drops or invalid consolidation output.

### REQ-I-407 - Compose skill artifacts into memory through the inbox

The package shall accept asynchronous Markdown inbox drops from skills and agents, process them deterministically with batch indexing, derive usage visibility from the recorded source, and expose bounded project- and trigger-based recall in the session bootstrap.

#### Verification

CLI/MCP and plugin tests process a sourced inbox entry and verify matching
visibility in search results; bootstrap tests check project and trigger bounds.
