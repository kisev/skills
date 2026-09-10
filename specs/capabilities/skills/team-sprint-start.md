# `team-sprint-start`

## Purpose

Start one explicitly selected sprint action from bounded team context.

## Triggers and Near-Misses

Trigger for sprint start; near-miss: roadmap review or sprint close.

## Inputs and Outputs

Input is context and fixed action. Output is structured start result and evidence.

## Workflow Stages

Resolve context, inspect prerequisites, execute action, validate, report.

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

## Example

`team-sprint-start` reports missing context without creating replacement state.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
