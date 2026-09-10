# `goal`

## Purpose

Run a bounded, auditable autonomous goal cycle tied to an OpenCode session.

## Triggers and Near-Misses

Trigger for explicit goal mode; near-miss: an ordinary implementation request.

## Inputs and Outputs

Input is goal, budget, and session. Output is bounded progress and final status.

## Workflow Stages

Resolve goal, set limits, execute, inspect status, report or escalate.

## Dependencies

OpenCode session state and task routing.

## Remote/Local Effects

Effects are limited to the confirmed goal scope; no implicit remote effects.

## Errors, Partial, Escalation

Budget exhaustion or missing state yields partial or blocked status.

## Unique Constraints

Durable attempts remain inspectable and are not silently discarded.

## Requirement

### REQ-F-110 - Bound autonomous goals

The skill shall enforce explicit goal scope and budget and report durable state.

## Example

`goal` stops at its token budget and leaves a resumable status.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
