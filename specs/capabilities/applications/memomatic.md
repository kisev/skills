---
review: {"components": ["memomatic"], "sources": ["apps/memomatic/src/*", "apps/memomatic/test/*", "packages/agentomatic/src/installer.ts", "packages/agentomatic/test/stage19.test.mjs"], "contracts": ["specs/architecture/08-crosscutting-concepts/security-trust-mutations.md"]}
---

# Application `memomatic`

## Purpose

Provide optional personal learning memory: selective capture, hybrid search, gated background consolidation, and rule-gated forgetting, with an MCP stdio server and a scheduled dream CLI sharing one data model. Compose durable outcomes from portable skill artifacts into memory through an asynchronous inbox. Models access memory through explicit MCP tool calls; no host plugin injects memory into system context.

## Triggers and Near-Misses

Used when durable engineering outcomes should survive sessions; near-miss: storing full transcripts or file scans, which memomatic never does.

## Inputs/Outputs

Input is an OpenCode session, an explicit tool call, an inbox drop from a skill or agent, or the scheduled sweep; output is annotated Markdown entries under `$XDG_STATE_HOME/memomatic/` (`MEMORY.md`, `USER.md`, `memory/YYYY-MM-DD.md`, `DREAMS.md`), a rebuildable SQLite index, and tool responses. Producers append Markdown entry lines to `$XDG_STATE_HOME/memomatic/inbox/` (`<source>-<stamp>-<token>.md`, mode 0600); rejected drops move to `inbox/rejected/`.

## Workflow Stages

Capture (explicit `memory_write` queuing an inbox drop, skill mirrors through the shared `memomatic_inbox.py` helper, or dream ingestion of session transcripts from the OpenCode database), process (`memomatic process`: validate lines, enforce `never-save`, deduplicate exact texts, supersede by `key`, route user-origin `target` entries, rebuild the index with embeddings — no model turns), rank (hybrid FTS5 and optional local embeddings, recency decay with half-life 30 days for episodic entries, importance multiplier, pinned and curated entries exempt), account usage (surfaced on search hits, useful on line fetches), gate promotion deterministically (relevance 0.30, frequency 0.24, diversity 0.15, recency 0.15, consolidation 0.10, richness 0.06), consolidate through one bounded model turn via `opencode run` (merge, supersede by key, bounded prior-entry loss 0.25, line budget), and report to `DREAMS.md` with content-addressed pre-images in `history/`. Dream and process serialize through a stale-tolerant run lock; inbox processing runs only on the systemd timer or a manual CLI run.

Every entry carries a `source` annotation; visibility derives from it: `team-*`, `gitlab`, and `spec-manage` entries may be quoted in team-facing artifacts, every other source is personal-only. Search responses expose the label. The MCP server exposes exactly `memory_search`, `memory_get`, `memory_write`, and `memory_forget` to all supported hosts. Agent-initiated retrieval is observable through host tool-call logs; choosing when to search remains the model's responsibility.

## Retrieval Contract

### REQ-F-543 - Retrieve bounded learned context with observable relevance

Search shall return relevant learned context or an empty result, not fill the
result limit with unrelated entries. A lexical match shall never reduce the
relevance score. Semantic-only candidates must pass `search.minSemanticScore`
(default 0.45) before ranking; lexical coverage must reach at least 0.5 and
`search.minScore`. The default general threshold remains 0.35. Scores are ranking
signals, not probabilities. Importance and age cannot admit a candidate that
failed relevance gates. Full token matches rank first; age decay still excludes
old low-ranking episodic entries.

Qwen3 embedding queries use an English task instruction in `Instruct`/`Query`
format; documents remain raw. Other models keep raw queries unless an explicit
`embedding.queryInstruction` is configured. The index records a fingerprint of
endpoint, model and document format. Missing/mismatched fingerprints or dimensions
require explicit reindexing. Invalid, incomplete or unavailable embeddings fail
visibly; failed indexing preserves the previous committed index. A completed
reindex replaces entries, vectors and the fingerprint in one transaction.

CLI `search --explain` and MCP `memory_search` with `explain: true` expose matched
tokens, lexical coverage, vector similarity, relevance, age/importance factors
and acceptance reason. Optional `project` limits recall to that exact project
plus user-level memory; unscoped entries are not guessed into a project. Returned
source, origin, kind and project identify learned context. Such context does not
override repository instructions, policy or current user decisions. No automatic
injection or full historical rebuild is introduced.

#### Verification

Regression tests cover exact matches, paraphrases, an unknown name, unrelated
queries, project filtering, inactive embedding endpoints, malformed vectors and
model changes with equal dimensions. Local Qwen3 calibration uses anonymized
positive and negative examples; thresholds remain configurable rather than a
claim of universal semantic accuracy.

## Dependencies

Node.js 22+, `node:sqlite`, optional OpenAI-compatible local embedding endpoint, configured OpenCode provider for dream model turns, presence-detected `$XDG_STATE_HOME/memomatic/inbox/` for skill producers. Agentomatic does not depend on memomatic; the standalone application is installed and connected to each host separately.

Dream session ingestion reads text parts from OpenCode's normalized `part`
table, ordered within each message; legacy databases with embedded message parts
remain readable. Dream invokes `opencode run --format json` with a positional
prompt and parses only text events, excluding tool and step metadata. Internal
Dream sessions remain excluded from extraction.

## Remote/Local Effects

No independent remote effect; dream model turns use the configured OpenCode provider and carry a `[memomatic-internal]` marker so ingestion never re-extracts them. Deletion is explicit (`memory_forget`) or enabled only by a `- auto-clean: older-than=Nd scope=episodic [source=name]` directive in `$XDG_CONFIG_HOME/memomatic/MEMORY_RULES.md`; `- never-save: <topic>` topics are rejected at write time, at inbox processing, and at dream extraction.

## Errors/Partial/Escalation

Invalid consolidation falls back to append-only within the line budget; unreadable session databases produce an empty ingestion window; `dry-run` reports without writes; malformed or forbidden inbox drops move to `rejected/` and are reported in the dream summary; a busy run lock fails with `another memomatic run is active`.

Dry-run uses an in-memory index and leaves the corpus, persistent index, run lock,
and session watermark unchanged; configured model and embedding calls may still
run. Without a model, session extraction is skipped without advancing its
watermark. Consolidation cannot authorize a curated `drop`; auto-clean selects
individual matching unpinned old entries rather than removing a whole daily file.

## Unique Constraints

Curated files are written only by dream consolidation, explicit user-origin writes, or inbox routing of user-origin targets; superseded entries are excluded from search and indexing; usage counters are keyed by stable entry identity (`key` annotation or content digest); state roots are absolute, normalized, symlink-free, with atomic mode-0600 writes; `memory_write` never touches corpus files directly.

## Requirement

### REQ-I-406 - Expose memomatic safely

> Lifecycle: `superseded` | Changed: `2026-09-28` | Reason: MCP replaces the selectable plugin and automatic context injection. | Replacement: [REQ-I-418](#req-i-418---expose-memory-through-explicit-mcp-tools)

Formerly exposed memomatic as a selectable OpenCode plugin with explicit or rule-gated forgetting and bounded consolidation.

### REQ-I-418 - Expose memory through explicit MCP tools

The application shall expose search, read, queued write, and explicit forgetting
through MCP without registering a host plugin or automatically injecting memory
into session context. Background processing remains a CLI or scheduled operation.
Forgetting remains explicit or rule-gated and consolidation stays bounded.
Explicit forgetting shares the processing lock, removes the indexed entry and
its vector, and adjusts subsequent line references without an embedding request.

Installer upgrades archive and remove unchanged manifest-owned legacy memomatic
wrappers; edited wrappers are conflicts and remain untouched. Users connect MCP
explicitly and restart their host. Existing memory, settings, inboxes, and timers
are preserved; the obsolete `projects` bootstrap mapping is ignored.

#### Verification

Memory regression tests reject traversal, sibling-prefix and symlink paths,
verify non-mutating dry-runs, retain unrelated entries during scoped cleanup,
and preserve curated entries on model drops or invalid consolidation output.
MCP tests exercise all four tools. Installer migration tests verify archival and
edited-file conflicts; public exports and the plugin catalog exclude memomatic.

### REQ-I-407 - Compose skill artifacts into memory through the inbox

The application shall accept asynchronous Markdown inbox drops from skills and agents, process them deterministically with batch indexing, and derive usage visibility from the recorded source for explicit retrieval.

#### Verification

CLI/MCP tests process a sourced inbox entry and verify matching visibility in search results.
