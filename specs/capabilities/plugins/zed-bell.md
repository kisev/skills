# Plugin `zed-bell`

## Purpose

Provide optional completion notification integration for Zed-compatible hosts.

## Triggers and Near-Misses

Selectable for notification; near-miss: changing task results or state.

## Inputs/Outputs

Input is plugin options and lifecycle event; output is a notification attempt/status.

## Workflow Stages

Resolve host/event, check options, notify, report safely.

## Dependencies

Host lifecycle event and Zed integration.

## Remote/Local Effects

Host-local notification effect; no repository or remote mutation.

## Errors/Partial/Escalation

Unavailable notification host is a bounded non-fatal status.

## Unique Constraints

Plugin is optional and separate from core routing.

## Requirement

### REQ-I-403 - Expose zed-bell safely

The package shall expose `zed-bell` as a selectable notification plugin without mutating task state.

## Example

The host selects `zed-bell` and receives a completion notification when supported.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
