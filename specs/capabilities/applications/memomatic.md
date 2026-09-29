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

Capture (explicit `memory_write` queuing an inbox drop, skill mirrors through the shared `memomatic_inbox.py` helper, or incremental ingestion from the OpenCode database), process (`memomatic process`: validate lines, enforce `never-save`, deduplicate exact texts, supersede by `key`, route user-origin targets, index changed text — no model turns), rank (hybrid retrieval, episodic age decay, pinned and curated exemptions), account usage, gate promotion deterministically, consolidate through bounded OpenCode model calls, and report to `DREAMS.md`. Content-addressed pre-images and compact extraction receipts live in `history/`. Dream and process serialize through a live-owner-aware run lock; processing runs on the timer or a manual CLI invocation.

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

Node.js 22.13+, `node:sqlite`, Commander, the build-materialized common CLI runtime, an optional OpenAI-compatible embedding endpoint, and a configured OpenCode provider for Dream. Agentomatic does not depend on memomatic; applications remain independently installed.

Dream session ingestion reads text parts from OpenCode's normalized `part`
table, ordered within each message; legacy databases with embedded message parts
remain readable. Dream uses one owned, authenticated loopback OpenCode server
per run or an explicitly selected existing server. Extraction sessions deny
tools; only response text and actual usage metadata are consumed. Internal Dream
sessions remain excluded from extraction.

## Remote/Local Effects

No independent remote effect; dream model turns use the configured OpenCode provider and carry a `[memomatic-internal]` marker so ingestion never re-extracts them. Deletion is explicit (`memory_forget`) or enabled only by a `- auto-clean: older-than=Nd scope=episodic [source=name]` directive in `$XDG_CONFIG_HOME/memomatic/MEMORY_RULES.md`; `- never-save: <topic>` topics are rejected at write time, at inbox processing, and at dream extraction.

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

## Unique Constraints

### REQ-F-544 - Drain a bounded snapshot with observable resumable processing

Normal Dream shall drain all eligible work captured at startup, without a default
session-count limit. Explicit limits bound sessions, request time, whole-run time,
fragment size and retries. `dream --plan` shall report pending work without model
calls or writes. `status`, command help and version shall not index or call models.
Per-call timeout defaults to 180 seconds, additional retries to one, fragment body
size to 24000 characters, and session idle age to ten minutes. Whole-run duration
and session-count limits default to zero (unlimited).

Local SQL shall select text parts before transferring payloads. Modern session,
message and part revisions allow unchanged sessions to bypass body parsing;
message/content fingerprints retain correctness for changed and legacy sessions.
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
live check validates the OpenCode HTTP contract without processing user history.

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
