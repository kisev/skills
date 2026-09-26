# Plugin `memomatic`

## Purpose

Provide optional personal learning memory: selective capture, hybrid search, gated background consolidation, and rule-gated forgetting, with OpenCode plugin tools, an MCP stdio server, and a scheduled dream CLI sharing one data model.

## Triggers and Near-Misses

Used when durable engineering outcomes should survive sessions; near-miss: storing full transcripts or file scans, which memomatic never does.

## Inputs/Outputs

Input is an OpenCode session, an explicit tool call, or the scheduled sweep; output is annotated Markdown entries under `$XDG_STATE_HOME/memomatic/` (`MEMORY.md`, `USER.md`, `memory/YYYY-MM-DD.md`, `DREAMS.md`), a rebuildable SQLite index, and tool responses.

## Workflow Stages

Capture (explicit `memory_write`, or dream ingestion of session transcripts from the OpenCode database), rank (hybrid FTS5 and optional local embeddings, recency decay with half-life 30 days for episodic entries, importance multiplier, pinned and curated entries exempt), account usage (surfaced on search hits, useful on line fetches), gate promotion deterministically (relevance 0.30, frequency 0.24, diversity 0.15, recency 0.15, consolidation 0.10, richness 0.06), consolidate through one bounded model turn via `opencode run` (merge, supersede by key, bounded prior-entry loss 0.25, line budget), and report to `DREAMS.md` with content-addressed pre-images in `history/`.

## Dependencies

OpenCode plugin API tools and `experimental.chat.system.transform`, `node:sqlite`, optional OpenAI-compatible local embedding endpoint, configured OpenCode provider for dream model turns.

## Remote/Local Effects

No independent remote effect; dream model turns use the configured OpenCode provider and carry a `[memomatic-internal]` marker so ingestion never re-extracts them. Deletion is explicit (`memory_forget`) or enabled only by a `- auto-clean: older-than=Nd scope=episodic` directive in `$XDG_CONFIG_HOME/memomatic/MEMORY_RULES.md`; `- never-save: <topic>` topics are rejected at write time and at dream extraction.

## Errors/Partial/Escalation

Invalid consolidation falls back to append-only within the line budget; unreadable session databases produce an empty ingestion window; bootstrap context injection never breaks a session; `dry-run` reports without writes.

## Unique Constraints

Curated files are written only by dream consolidation or explicit user-origin writes; superseded entries are excluded from search and indexing; usage counters are keyed by stable entry identity (`key` annotation or content digest); state roots are absolute, normalized, symlink-free, with atomic mode-0600 writes.

## Requirement

### REQ-I-406 - Expose memomatic safely

The package shall expose `memomatic` as a selectable plugin whose forgetting is explicit or rule-gated and whose consolidation stays inside deterministic bounds.
