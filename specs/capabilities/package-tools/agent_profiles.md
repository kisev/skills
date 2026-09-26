# Package Tool `agent_profiles`

- Status: withdrawn
- Status changed: 2026-09-16
- Reason: Profile management remains available through `agentomatic agent` and `critic` commands.

## Purpose

Historical capability record for the retired OpenCode package tool.

## Triggers and Near-Misses

Trigger for profile management; near-miss: direct config editing.

## Inputs/Outputs

Input is action, optional scope defaulting to project, profile values, and
confirmation digest; output is inventory/plan/result.

## Workflow Stages

Resolve ownership, list or preview, confirm, apply atomically, validate, report.

## Dependencies

Profile manifest, host config paths, lock/recovery lifecycle.

## Remote/Local Effects

Bounded global/project local configuration effects.

## Errors/Partial/Escalation

Collisions, stale receipts, symlinks, and failures roll back or escalate.

## Unique Constraints

Exact semantic ownership and restart behavior are preserved.

## Requirement

### REQ-F-504 - Mutate profiles transactionally

Status: withdrawn on 2026-09-16 because profile management is now CLI-only.

Former requirement: the tool shall require preview and fresh confirmation and
preserve user-owned configuration.

## Example

`agent_profiles` rejects an exact-name user collision before apply.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
