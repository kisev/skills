# `commit-msg`

## Purpose

Generate one concise English commit message from current changes.

## Triggers and Near-Misses

Trigger for commit message generation; near-miss: committing or amending history.

## Inputs and Outputs

Input is staged or working-tree diff. Output is a proposed message only.

## Workflow Stages

Resolve changed paths, inspect diff and history, classify, report message.

## Dependencies

Git status, diff, and recent log.

## Remote/Local Effects

Local reads only; never writes, commits, or pushes.

## Errors, Partial, Escalation

No changes or mixed intent is reported for clarification.

## Unique Constraints

Staged changes have priority and secrets are not repeated.

## Requirement

### REQ-F-106 - Keep message generation read-only

The skill shall generate a message without changing Git history or the worktree.

## Example

`commit-msg` proposes an English message from staged specification changes.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
