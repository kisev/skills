# Plugin `rtk`

## Purpose

Provide optional compact command output integration.

## Triggers and Near-Misses

Selectable for output compression; near-miss: dropping failure evidence.

## Inputs/Outputs

Input is plugin options and command output; output is compact preserved output.

## Workflow Stages

Resolve eligibility, invoke adapter, preserve status/errors, report.

## Dependencies

RTK adapter and host command execution.

## Remote/Local Effects

No independent remote effect; wrapped command effects remain visible.

## Errors/Partial/Escalation

Unsupported output retains original failure and escalates.

## Unique Constraints

Plugin selection does not change public capability inventory.

## Requirement

### REQ-I-402 - Expose rtk safely

The package shall expose `rtk` as a selectable plugin without suppressing command evidence.

## Example

The host enables `rtk` while retaining a failing command's exit status.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
