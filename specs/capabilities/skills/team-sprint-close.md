# `team-sprint-close`

## Purpose

Close one explicitly selected sprint action with structured evidence.

## Triggers and Near-Misses

Trigger for sprint close; near-miss: starting a sprint or general retro.

## Inputs and Outputs

Input is the fixed action and an automatically resolved default private profile
or explicit legacy context. Output is a bounded close report and state result.

## Workflow Stages

Resolve or self-setup the profile, inspect state, execute the fixed action,
validate the digest, and report.

## Dependencies

Shared team runtime and owned sprint state.

## Remote/Local Effects

Declared local state mutation; no implicit external publication.

## Errors, Partial, Escalation

Stale/tampered plans and invalid syntax are structured failures.

## Unique Constraints

Close actions use the shared digest and fixed-action contract.

## Requirement

### REQ-F-128 - Confirm sprint close state

The skill shall close only the selected sprint action with fresh validated evidence.

## Example

`team-sprint-close` rejects a stale close plan and reports the required recheck.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
