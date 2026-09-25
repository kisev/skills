# ADR-0010: Separate review orchestration and guarded publication

## Status

Accepted, 2026-09-25.

## Context and Problem Statement

The shared GitLab runtime controlled review-specific stages and imported its own
consumer. Publication documentation disagreed about advisory markers and verified
remote results. OpenCode routing selected a primary-only review agent that the
manager could not call.

## Decision Drivers

Preserve independent review, keep portable installation self-contained, establish
one owner per mechanism, and make an uncertain publication outcome distinguishable
from a safe retry.

## Considered Options

- Retain manual `glab` commands and advisory markers, correcting documentation only.
- Add a user-invoked single-action helper with fresh preconditions and postconditions.
- Execute an approved batch with resumable partial publication.

## Outcome

Use the single-action helper. Review preparation remains non-publishing; the user
starts each mutation independently. A persisted reservation precedes process start,
and a fresh read establishes success. Unknown outcomes block writes until a
bounded read-only inspection proves the effect or the user explicitly accepts a
retry after the effect remains unobserved. The helper preserves redacted failure
diagnostics and offers the exact recovery commands. No batch executor or automatic
retry exists.

Review owns its orchestration and calls shared evidence, validation, and process
primitives. OpenCode manager delegates the primary review to the dual-mode review
agent; that agent selects independent critics according to the skill contract.
Explicitly requested fixing is a separate phase, not an implicit review effect.

## Consequences

Ownership and dependency direction become explicit. Publication gains stronger
guarantees at the cost of a private ledger, POSIX requirements, additional reads,
and the possibility of a blocked unknown result. Snapshot validation and hostless
tests do not establish the quality of model reasoning.

## Compatibility, Migration, and Rollback

Existing review plans remain readable. Users regenerate actions against fresh
evidence; advisory markers are never upgraded into verified receipts. Existing
agent names and model configuration remain supported, with changed rendered
permissions and modes applied by the installer. Rolling back code does not erase
review artifacts or publication state; an older version cannot promise guarded
publication and users must not replay uncertain actions through it.

## Verification

Tests cover nested routing, current-plan membership, digest and body integrity,
stale conversations, dependent thread closure, replay, process-start failure,
ambiguous results, and read-only recovery. Package smoke verifies host discovery.
Tests also cover delayed postconditions, retained diagnostics, and explicit retry
after an absent effect.

## Links

- [REQ-F-105](../../capabilities/skills/code-review.md#req-f-105---review-exact-changes)
- [REQ-F-301](../../capabilities/agents/manager.md#req-f-301---bind-manager-orchestration)
- [REQ-F-305](../../capabilities/agents/review.md#req-f-305---produce-structured-review-reports)
- [ADR-0007](0007-make-administration-cli-only.md)
