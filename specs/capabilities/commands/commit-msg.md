# `/commit-msg`

## Purpose

Expose the `commit-msg` skill as a read-only command adapter.

## Triggers and Near-Misses

Routes message generation; near-miss: committing history.

## Inputs/Outputs

Arguments are untrusted; output is one proposed English message.

## Workflow Stages

Select, pass, inspect diff, generate, report.

## Dependencies

`commit-msg` and native Skill loading.

## Remote/Local Effects

Local reads only; command never commits.

## Errors/Partial/Escalation

No changes or mixed intent is escalated.

## Unique Constraints

Staged-change priority is retained.

## Requirement

### REQ-I-206 - Route the commit-msg command

The command shall load exactly `commit-msg` without changing Git history.

## Example

`/commit-msg` returns a message proposal only.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
