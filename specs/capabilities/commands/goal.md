# `/goal`

## Purpose

Expose the bounded `goal` skill command.

## Triggers and Near-Misses

Routes explicit goal mode; near-miss: ordinary tasks.

## Inputs/Outputs

Arguments provide goal and budget; output is durable goal status.

## Workflow Stages

Select, pass, bound, execute, inspect, report.

## Dependencies

`goal` and session state.

## Remote/Local Effects

Effects remain within confirmed goal scope.

## Errors/Partial/Escalation

Budget and state failures are explicit.

## Unique Constraints

No hidden autonomous continuation.

## Requirement

### REQ-I-210 - Route the goal command

The command shall load exactly `goal` and preserve explicit budget boundaries.

## Example

`/goal` starts a bounded session goal.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
