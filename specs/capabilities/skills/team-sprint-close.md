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

### REQ-F-512 - Make closing artifacts provenance-bound

Closing artifacts shall end with a data-sources section rendered from the
private evidence store, listing each contributing source's kind, exact
location, collected window or point timestamp, completeness, and collection
time as specified by REQ-F-509, and each written artifact shall be snapshotted
in the store with its period and contributing source keys. GitLab delivery
evidence collected through the bundled metrics collector shall reuse complete
stored windows and fetch only the missing delta.

## Example

`team-sprint-close` rejects a stale close plan and reports the required recheck.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
