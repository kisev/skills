# `team-sprint-start`

## Purpose

Start one explicitly selected sprint action from bounded team context.

## Triggers and Near-Misses

Trigger for sprint start; near-miss: roadmap review or sprint close.

## Inputs and Outputs

Input is the fixed action and an automatically resolved default private profile
or explicit legacy context. Output is structured start result and evidence.

## Workflow Stages

Resolve or self-setup the profile, inspect prerequisites, execute the fixed
action, validate, and report.

## Dependencies

Shared team runtime, context, and owned state.

## Remote/Local Effects

Declared local state effects; no implicit external effects.

## Errors, Partial, Escalation

Invalid prerequisites or malformed state block the action.

## Unique Constraints

The fixed action and state owner are explicit in every result.

## Requirement

### REQ-F-129 - Keep sprint start bounded

The skill shall start only the selected sprint action after validating its prerequisites.

### REQ-F-511 - Make planning artifacts provenance-bound

Planning artifacts shall end with a data-sources section rendered from the
private evidence store, listing each contributing source's kind, exact
location, collected window or point timestamp, completeness, and collection
time as specified by REQ-F-509, and each written artifact shall be snapshotted
in the store with its period and contributing source keys.

## Example

`team-sprint-start` reports missing context without creating replacement state.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
