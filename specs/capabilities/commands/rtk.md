# `/rtk`

## Purpose

Expose output summarization through the `rtk` skill.

## Triggers and Near-Misses

Routes verbose output; near-miss: deleting evidence.

## Inputs/Outputs

Arguments select eligible output; output retains errors and status.

## Workflow Stages

Select, pass, compress, preserve errors, report.

## Dependencies

`rtk` adapter.

## Remote/Local Effects

Same command effects as the wrapped command.

## Errors/Partial/Escalation

Unsupported adapter use escalates.

## Unique Constraints

Exit status and paths remain visible.

## Requirement

### REQ-I-217 - Route the rtk command

The command shall load exactly `rtk` without hiding actionable failure evidence.

## Example

`/rtk` summarizes a long test output.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
