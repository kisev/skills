# ADR-0010: Separate review orchestration and manual publication

## Status

Accepted, 2026-09-25. Publication decision amended 2026-10-01.

## Context and Problem Statement

Review needs independent analysis, exact evidence, and consistent local artifacts.
The original guarded publication helper introduced receipts, reservations, expiry,
and postcondition reads. Network interruption and orphaned locks prevented even
inspection, while synchronous checks froze the TUI. Users already deliberately
choose mutations and inspect their effects in GitLab.

## Decision Drivers

Preserve review quality and ownership, keep manual commands and an interactive
interface equally useful, and avoid a second publication decision-maker.

## Considered Options

- Extend guarded publication with lock recovery and additional remote checks.
- Use direct manual `glab` commands with the same operations in the TUI.
- Execute an automatically resumable batch.

## Outcome

Use direct manual commands in `runbook.md` and an asynchronous TUI executor without
a shell. Remove publication reservations, receipts, persistent locks, expiry,
polling, and automatic freshness/replay decisions. One send reports command exit
and diagnostics. The user checks GitLab and chooses repetition. Replies and thread
state changes remain independently runnable. Cancellation only stops local waiting.

Review preparation remains non-publishing and preserves exact analysis bindings.
Targeted plan repair and changed-evidence refresh retain earlier work without
repeating unrelated analysis. Changed conclusions require targeted independent
review. OpenCode orchestration still delegates primary review and independent
critics according to the skill contract; explicitly requested fixing remains a
separate phase.

## Consequences

Manual publication is faster and cannot be blocked by persisted publication state.
It does not promise exactly-once delivery or independent verification of a remote
effect. A repeat after timeout may duplicate a comment; the user accepts this
tradeoff. Structural checks cannot prove semantic review quality.

## Compatibility, Migration, and Rollback

New contract-7 guided plans support targeted repair. Old plans stay readable history
without automatic migration or execution of their guarded commands. Upgrades do
not delete live legacy state. A rollback does not make uncertain old sends safe.
Other profiles keep their own guarded publication policies.

## Verification

Tests cover command parity, no publication GETs/state, failures, repeated sends,
cancellation, responsive UI, exact fixes, retained critique, atomic local repair,
CI refresh, and historical read-only behavior. PTY smoke tests exercise the CLI.

## Links

- [REQ-F-105](../../capabilities/skills/code-review.md#req-f-105---review-exact-changes)
- [REQ-F-301](../../capabilities/agents/manager.md#req-f-301---bind-manager-orchestration)
- [REQ-F-305](../../capabilities/agents/review.md#req-f-305---produce-structured-review-reports)
- [ADR-0007](0007-make-administration-cli-only.md)
