# `team-retro`

## Purpose

Run one explicitly selected retrospective action against team context.

## Triggers and Near-Misses

Trigger for a retrospective action; near-miss: roadmap or sprint planning.

## Inputs and Outputs

Input is explicit context and action. Output is structured retrospective material.

## Workflow Stages

Resolve context, inspect state, execute fixed action, validate, report.

## Dependencies

Shared team workflow runtime and owned state.

## Remote/Local Effects

Bounded local state effects; external effects only if declared by the action.

## Errors, Partial, Escalation

Missing context or invalid action returns structured JSON failure.

## Unique Constraints

One fixed action is selected and state ownership is explicit.

## Requirement

### REQ-F-126 - Keep retrospective actions explicit

The skill shall execute only the selected fixed action against its declared team context.

## Example

`team-retro` refuses an unknown action before reading or writing state.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
