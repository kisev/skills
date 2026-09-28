# ADR-0016: Unify task runtime and explicit recall

- Status: accepted
- Date: 2026-09-28
- Supersedes: none

## Context

The user selected TypeScript for both standalone applications and asked for
relevant, explainable memory retrieval. Memomatic already uses TypeScript and
npm; taskmatic previously split a Python skill runner from a Python web app.
Raw Qwen3 search queries and a score blend that could penalize lexical evidence
produced unrelated hits. Rewriting memomatic in Python would mix a language
migration with the search correction without simplifying publication.

## Decision

Keep memomatic in TypeScript and move taskmatic CLI, MCP, exports and viewer to
the independent `@kisev/taskmatic` npm package. Retain SQLite v1 and existing state
paths, snapshots and tool names. The skill remains portable instructions with an
explicit application prerequisite; it is no longer a self-contained executable.
New npm-name bootstrap and host/service changes remain confirmed operations.

Correct memory retrieval before ranking: model-appropriate query instructions,
lexical coverage, semantic thresholds, exact-match priority, project filtering,
index/model compatibility and visible explanations. Preserve time decay, rules,
inbox processing and Dream. Do not add an LLM reranker or full corpus rebuild.

## Memory Principles and Tradeoffs

The [Z.ai memory principles](https://docs.z.ai/devpack/resources/memory-mechanism)
support separating human-authored instruction memory from learned experience,
scoped retrieval, inspectable storage and controlled updates. Memomatic returns
learning-memory evidence, not a new policy authority. Project filters narrow
context; user-level entries remain reusable. Session context stays in the host,
and retrieval remains an explicit MCP call under ADR-0015.

Use the [Qwen3 model's query/document guidance](https://huggingface.co/Qwen/Qwen3-Embedding-4B)
for embeddings. A small local calibration distinguishes representative positive
and negative queries but is not a general accuracy guarantee. High thresholds
can miss weak paraphrases; settings and explanations make that tradeoff visible.

## Compatibility and Rollback

Reindexing changes derived SQLite/vector data, not Markdown memory contents.
An interrupted or failed vector rebuild does not replace the prior index.
Taskmatic opens the prior schema without destructive conversion, so rollback
can reuse the old runtime and current database. Retain consistent backups and
the old installation until host/MCP/viewer checks pass. CLI and service paths
change explicitly; an old uv/pipx alias may shadow the npm alias.

## Verification

See [REQ-F-542](../../capabilities/skills/taskmatic.md#req-f-542---preserve-taskmatic-data-through-the-typescript-runtime)
and [REQ-F-543](../../capabilities/applications/memomatic.md#req-f-543---retrieve-bounded-learned-context-with-observable-relevance).
