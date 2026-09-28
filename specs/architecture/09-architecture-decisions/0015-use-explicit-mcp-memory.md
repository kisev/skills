# ADR-0015: Use explicit MCP memory

- Status: accepted
- Date: 2026-09-28
- Supersedes: [ADR-0012](0012-compose-memomatic-learning-memory.md) and [ADR-0013](0013-compose-memomatic-artifact-inbox.md)

## Context and Drivers

The OpenCode plugin duplicated the MCP memory tools and injected context that
other hosts did not receive. The agreed behavior is model-initiated retrieval
through visible tool calls in OpenCode, Kilo, and MiMo, with no automatic recall.

## Considered Options

1. Keep native tools and bootstrap in OpenCode and use MCP elsewhere. This retains
   implicit context and different behavior across hosts.
2. Use MCP tools everywhere and retain a bootstrap-only plugin. This avoids
   duplicate tools but still injects memory and requires host-specific support.
3. Remove the plugin and use MCP tools plus the independent processing CLI.
   This matches the explicit-retrieval requirement and simplifies installation.

## Decision

Choose option 3. [REQ-I-418](../../capabilities/applications/memomatic.md#req-i-418---expose-memory-through-explicit-mcp-tools)
owns the MCP-only agent interface. The memory corpus, rules, embeddings, explicit
forgetting, bounded consolidation, and scheduled Dream engine from ADR-0012 stay
in the standalone application. The asynchronous inbox and source-derived
visibility from ADR-0013 remain under
[REQ-I-407](../../capabilities/applications/memomatic.md#req-i-407---compose-skill-artifacts-into-memory-through-the-inbox).
Agentomatic no longer imports or depends on memomatic. No session hook reads or
injects memory. Dream still reads OpenCode history; MCP does not import the
histories of other hosts.

## Compatibility and Migration

The plugin export and selection, bootstrap helpers, and `projects` settings map
are removed. Old settings remain readable; the obsolete map is ignored. Entry
annotations and stored data are preserved. Confirmed installer upgrades archive
unchanged owned wrappers and reject edited wrappers as conflicts. Users connect
the standalone MCP server and restart hosts; upgrading an npm dependency alone
does not retire deployed wrappers. Manually configured plugin imports require
manual removal.

## Consequences and Risks

All hosts use one observable tool interface. Models decide when to search and can
omit a useful lookup; explicit user requests or host instructions can encourage
retrieval but do not guarantee a tool call. Background processing remains
independent of host sessions. There is no new storage or credential boundary.

## Rollback and Reversibility

The MCP connection can be disabled without deleting memory or stopping Dream.
Restoring the previous plugin requires an explicitly selected older package and
its wrapper; it is not an automatic fallback. No corpus migration is needed.
