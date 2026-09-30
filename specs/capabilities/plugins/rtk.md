# Plugin `rtk`

## Purpose

Provide optional compact command output integration, deployed by default, with local observability.

## Triggers and Near-Misses

Selectable for output compression; near-miss: dropping failure evidence.

## Inputs/Outputs

Input is plugin options and command output; output is compact preserved output plus classified local statistics.

## Workflow Stages

Resolve eligibility, invoke adapter, preserve status/errors, classify the event, record counters in the user state directory, report.

## Dependencies

RTK adapter and host command execution.

## Remote/Local Effects

No independent remote effect; wrapped command effects remain visible. Statistics persist only in `$XDG_STATE_HOME/opencode/skills/rtk/stats.json` (mode 0600) with a capped recent-event list and no command output contents.

## Errors/Partial/Escalation

Unsupported output retains original failure and escalates. Statistics failures never affect compression (fail-open).

## Unique Constraints

Plugin selection does not change public capability inventory. The installer preselects `rtk` for fresh deployments and never edits `opencode.json`: deployed wrapper files in the `plugins` directory are auto-loaded by the host. An explicit `--plugins none` selection and a previously installed manifest selection are preserved.

## Requirement

### REQ-I-402 - Expose rtk safely

The package shall expose `rtk` as a selectable plugin without suppressing command evidence.

### REQ-I-405 - Make rtk observable and default-on

The package shall deploy the `rtk` wrapper with the default installer selection, record classified compression events (compressed-rtk, truncated-head-tail, rtk-unavailable, ineligible, below-threshold) with character savings in private local state, and expose the summary through the `rtk.observability` doctor check and the `/rtk-stats` command.

## Example

The host enables `rtk` while retaining a failing command's exit status.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
