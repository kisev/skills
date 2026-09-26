# ADR-0012: Compose memomatic learning memory

- Status: accepted
- Date: 2026-09-26
- Status changed: none
- Supersedes: none
- Superseded by: none

## Context and problem statement

OpenCode sessions lose durable engineering outcomes: standing decisions,
discoveries, rejected approaches, and session summaries. Evaluated memory
solutions (engram, opencode-mem, mcp-memory-service, cioffiAI/opencode-memory,
Macrodata) each miss at least one of selective capture, autonomous background
consolidation, configurable forgetting, or execution through the user's
configured OpenCode provider with model and reasoning variant.

## Decision drivers

- Capture only significant outcomes; never scan whole files or store full transcripts.
- Separate agent learning memory from human instruction files (AGENTS.md, rules).
- Markdown as the source of truth with a rebuildable index; local embeddings.
- Background consolidation on a schedule independent of a running OpenCode UI.
- Forgetting defaults safe: ranking decay and supersession, deletion only explicit
  or rule-gated; pinning exempt from decay.
- Reuse the OpenClaw memory architecture where it is proven: tiers, provenance,
  deterministic gates with model judgment inside them, review trail.

## Considered options

- Adopt or extend an existing OpenCode memory plugin or MCP server.
- Build a memory system inside a portable skill using the shared Python runtime.
- Ship memomatic as the standalone `@kisev/memomatic` package under `apps/memomatic`
  with its own
  XDG namespace, OpenCode plugin tools, an MCP stdio server, and a dream CLI.

## Outcome

`@kisev/agentomatic` depends on `@kisev/memomatic` (and both on `@kisev/safe-fs`):
memomatic is a personal learning-memory subsystem with
tiered corpus (`MEMORY.md`, `USER.md`, daily notes, `DREAMS.md`), an annotated
entry format (`<!-- key/status/origin/observed/project/importance/trigger/pinned -->`),
a SQLite index with FTS5 keyword search, optional local embeddings through an
OpenAI-compatible endpoint, and a deterministic promotion gate (relevance,
frequency, diversity, recency, consolidation, richness) whose passing candidates
are consolidated by one bounded model turn executed through `opencode run` with
the configured model and variant. The dream sweep ingests session transcripts
read-only from the OpenCode database, appends validated extractions to daily
notes, applies consolidation with a bounded prior-entry loss, archives pre-images
content-addressed, and reports to `DREAMS.md`. Manual directives live in
`$XDG_CONFIG_HOME/memomatic/MEMORY_RULES.md` (`never-save` topics, opt-in
`auto-clean`); nothing else may delete memory. State lives under
`$XDG_STATE_HOME/memomatic/` as its own XDG namespace.

## Consequences

### Positive

- One data model serves the OpenCode plugin tools, the MCP server, and the CLI.
- Deterministic gates and bounded rewrites keep model output inside safe bounds.
- Versioned pre-images and DREAMS.md give an auditable consolidation trail.
- Session ingestion runs while OpenCode is closed, driven by systemd user units.

### Negative

- Escalation recall (a blocking sub-agent lane) is out of scope for this iteration.
- Vectors are stored as blobs with in-process cosine ranking, which bounds corpus scale.
- Promotion thresholds are starting values and need calibration on real sessions.

## Compatibility

New opt-in plugin selection `memomatic`; existing selections and public exports
of `@kisev/agentomatic` are unchanged apart from the added export. No
portable skill or shared runtime adopts memomatic behavior.

## Migration

None: memomatic state starts empty in its dedicated XDG namespace and never
reinterprets other portable state.

## Rollback

Deselect the `memomatic` plugin, remove its systemd user units, and delete
`$XDG_STATE_HOME/memomatic` and `$XDG_CONFIG_HOME/memomatic`; no other system
depends on them.

## Reversibility

Reversal is low: the subsystem is self-contained and no external data migration
is involved.

## Risks

- Model-returned JSON is parsed defensively; invalid or unavailable decisions
  fall back to append-only behavior, mirroring the OpenClaw safety pattern.
- The OpenCode session database schema is read defensively; unreadable databases
  yield an empty ingestion window instead of a failed sweep.
- Auto-clean is off unless an explicit MEMORY\_RULES.md directive enables it.

## Links

- Requirements: [REQ-I-406](../../capabilities/plugins/memomatic.md#req-i-406---expose-memomatic-safely)
- Related ADRs: [ADR-0008](0008-compose-persistent-gitlab-task-triage.md)
