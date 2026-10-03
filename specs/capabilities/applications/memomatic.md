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

Capture (explicit `memory_write` queuing an inbox drop, skill mirrors through the shared `memomatic_inbox.py` helper, or incremental ingestion from the OpenCode database through the separate `memomatic sessions` command), process (`memomatic process`: validate lines, enforce `never-save`, deduplicate exact texts, supersede by `key`, route user-origin targets, index changed text — no model turns), rank (hybrid retrieval, episodic age decay, pinned and curated exemptions), account usage, gate promotion deterministically, consolidate through bounded OpenCode model calls, and report to `DREAMS.md`. Content-addressed pre-images and compact extraction receipts live in `history/`. Sessions, Dream, and process serialize through a live-owner-aware run lock; each runs on its own timer or a manual CLI invocation. Dream follows the OpenClaw consolidation shape: it never reads OpenCode history; it drains the inbox, promotes usage-gated episodic entries into `MEMORY.md`, applies the bounded consolidation rewrite, and archives decayed entries.

Promotion weights remain relevance 0.30, frequency 0.24, diversity 0.15, recency
0.15, consolidation 0.10 and richness 0.06. Consolidation keeps the configured
line budget and bounded prior-entry loss (default 0.25); curated drops remain
rejected by deterministic application rather than relying on the prompt.

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
`embedding.queryInstruction` is configured; an explicit empty value disables
wrapping. Optional `embedding.queryPrefix` and `embedding.documentPrefix`
settings format queries and documents independently, defaulting to raw text.
Embedding and reranker endpoints are configured independently, each with a full
URL, model, optional `bearerEnv` naming the environment variable that holds a
Bearer token, a configurable per-request timeout that may cover cold model
loads, and request limits (`maxBatchTexts`, `maxTextChars`, `candidates`,
`minScore`, `maxDocuments`, `maxChars`). No server is built in, both services
default to disabled, and tokens never reach logs. The index records a
fingerprint of endpoint, model and document format including prefix and chunk
budget; query-only and reranker settings are excluded, so changing them never
requires recomputing vectors. Missing/mismatched fingerprints or dimensions
require explicit reindexing. Invalid, incomplete, timed-out or unavailable
enabled endpoints fail visibly in CLI and MCP without falling back to another
search mode; failed indexing preserves the previous committed index. A
completed reindex replaces entries, vectors and the fingerprint in one
transaction.

Texts longer than `embedding.maxTextChars` are split at paragraph, line or
space boundaries; chunk vectors are mean-pooled onto one vector per entry, so
chunked entries surface once. Reranker documents are chunked so the query, one
document chunk and the server-side template stay inside `reranker.maxChars`,
and chunk scores aggregate by maximum per entry. Character budgets are a
conservative proxy of roughly two characters per token, not exact tokenization;
defaults target the common 4096-token input budget.

An enabled reranker collects a bounded wide candidate set of up to
`reranker.candidates` entries from lexical and vector search before the strict
relevance gates, applies the project filter before sending, and posts
`{model, query, documents, top_n}` to the configured `/rerank`-style endpoint,
reading `results[].index` and `results[].relevance_score`. Reranker scores
become the final relevance and order without an unconditional literal-match
priority; `reranker.minScore` drops weak results. Reranker scores stay ranking
signals, not universal probabilities.

CLI `search --explain` and MCP `memory_search` with `explain: true` expose matched
tokens, lexical coverage, vector similarity, relevance, age/importance factors
and acceptance reason, plus the candidate count and threshold for reranked
results. Optional `project` limits recall to that exact project
plus user-level memory; unscoped entries are not guessed into a project. Returned
source, origin, kind and project identify learned context. Such context does not
override repository instructions, policy or current user decisions. No automatic
injection or full historical rebuild is introduced.

#### Verification

Regression tests cover exact matches, paraphrases, an unknown name, unrelated
queries, project filtering, inactive embedding endpoints, malformed vectors and
model changes with equal dimensions, the documented vLLM-style embeddings and
`/rerank` contract with permuted response indices, Bearer authentication
without token leakage, chunking with per-input pooling, document-format-change
migration with preserved indexes on failure, explicit timeout and malformed
reranker failures, and reranker ordering that ranks a relevant paraphrase above
a literal match. Local Qwen3 calibration uses anonymized
positive and negative examples; thresholds remain configurable rather than a
claim of universal semantic accuracy. Live server availability and concrete
threshold quality are not asserted.

## Dependencies

Node.js 22.13+, `node:sqlite`, Commander, `jsonc-parser`, the build-materialized common CLI runtime, optional OpenAI-compatible embedding and `/rerank`-style reranking endpoints, and a configured OpenCode V2 provider for Sessions extraction and Dream consolidation (a legacy `dream` extraction configuration migrates to `sessions` until overridden). Agentomatic does not depend on memomatic; applications remain independently installed.

Session ingestion (the `sessions` command) reads user and assistant text from
OpenCode's native V2 `session_v2`/`session_message` projections in sequence
order; reasoning, tool, and synthetic parts stay unread. A pre-V2 database fails
with a visible instruction to start V2 so it migrates history first. Sessions
use one owned, authenticated loopback OpenCode V2 server per run or an
explicitly selected existing server. Extraction sessions deny tools through
ordered deny-all permissions; only response text is consumed because transient
V2 generation reports no exact token usage. Internal extraction sessions remain
excluded from later extraction.

## Remote/Local Effects

No independent remote effect; sessions and dream model turns use the configured OpenCode provider and carry a `[memomatic-internal]` marker so ingestion never re-extracts them. Deletion is explicit (`memory_forget`) or enabled only by a `- auto-clean: older-than=Nd scope=episodic [source=name] [unused-after=Nd]` directive in `$XDG_CONFIG_HOME/memomatic/MEMORY_RULES.md`; the optional `unused-after` suffix archives old episodic entries with zero useful recalls earlier than the age-only cutoff and is inactive unless declared. `- never-save: <topic>` topics are rejected at write time, at inbox processing, and at session extraction.

## Errors/Partial/Escalation

Invalid consolidation falls back to append-only within the line budget. A missing
default session database is visibly skipped; an explicitly supplied missing or
unreadable database fails. Malformed or forbidden inbox drops move to `rejected/`.
A busy run lock fails with `another memomatic run is active`. A live owner is not
evicted merely because a sweep exceeds thirty minutes.

Dry-run uses an in-memory index and leaves the corpus, persistent index, run lock,
and session watermark unchanged; configured model and embedding calls may still
run. Without a model, session extraction is skipped without advancing its
watermark. Consolidation cannot authorize a curated `drop`; auto-clean selects
individual matching unpinned old entries rather than removing a whole daily file.

### REQ-F-545 - Expose the queue and split extraction from consolidation

The application shall expose OpenCode session extraction as the standalone
`sessions` command and keep `dream` as consolidation only: inbox processing,
usage-gated promotion, bounded rewrite, and rule-gated archiving. Two
independent timers schedule the sweeps, and both commands serialize through the
shared run lock. `status` shall report the pending queue without model calls or
writes: pending inbox files, the session backlog from the OpenCode database
(or `null` when it does not exist), the current promotion-candidate count, and
the last dream/sessions run timestamps recorded in the index metadata.

#### Verification

CLI tests verify help and malformed-argument handling for both commands, the
status queue report against a fixture database and inbox, and the no-database
`null` backlog; regression tests cover watermark preservation and last-run
recording for each sweep.

## Unique Constraints

### REQ-F-544 - Drain a bounded snapshot with observable resumable processing

Normal Sessions shall drain all eligible work captured at startup, without a default
session-count limit. Explicit limits bound sessions, request time, whole-run time,
fragment size and retries. `sessions --plan` and `dream --plan` shall report
pending work without model calls or writes. `status`, command help and version
shall not index or call models.
Per-call timeout defaults to 180 seconds, additional retries to one, fragment body
size to 24000 characters, and session idle age to ten minutes. Whole-run duration
and session-count limits default to zero (unlimited).

Local SQL shall select message rows before transferring payloads. Session and
ordered-message revisions allow unchanged sessions to bypass body parsing;
revision-list fingerprints retain correctness for changed sessions.
Long messages are processed through bounded fragments without truncating the end
or splitting Unicode surrogate pairs. Only adjacent exact duplicates of the same
role are removed; semantic importance is not guessed by a local filter. Fragments
retain ordered roles, source IDs and a bounded preceding context overlap.

Completed extraction results shall be persisted as private versioned receipts
before idempotent corpus application and checkpoint advancement. Cancellation or
later failure preserves completed work and avoids paying again for saved model
responses. Existing legacy creation-time cursors require one conservative replay
of eligible history; this retains the corpus and is visible in diagnostics and
documentation. Source histories are never stored wholesale in memomatic.

Indexing shall reuse vectors only for unchanged text and matching model identity,
embedding changed entries in bounded batches. Incompatible dimensions fail before
index commit. `index --force` bypasses that cache. Unchanged consolidation inputs
reuse a prior response. The index may lag committed Markdown after interruption;
a subsequent successful index pass repairs it.

Progress shall expose stages, elapsed time, fragment counts, retries, cache counts,
sent characters and actual token usage when available. Wait heartbeats identify
an outstanding model request; no fictitious percentage or token certainty is
reported. Diagnostic logs exclude transcript and authentication content. No
parallel model requests are started by default. An owned OpenCode process group
is terminated on exit; an attached server is never stopped. Model sessions are
aborted on timeout/cancellation and persistent checkpoints remain available.

#### Verification

Tests cover continuation and edits of old sessions, complete long-message tails,
revision-cache hits, interrupted extraction and response reuse, model timeout and
retry events, unchanged embedding reuse and force, live-owner locks, safe help and
status, JSON/stdout separation, and owned-server reuse and shutdown. A bounded
live check validates the native V2 OpenCode HTTP, permission-denial, and
read-only database contract without processing user history.

### Corpus constraints

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
