# `team-roadmap`

## Purpose

Produce a roadmap view from explicit team context without turning it into execution.

## Triggers and Near-Misses

Trigger for roadmap action; near-miss: sprint close or implementation planning.

## Inputs and Outputs

Input is explicit context and action. Output is a structured roadmap view.

## Workflow Stages

Resolve context, inspect owned state, run action, validate, report.

## Dependencies

Shared team workflow runtime and context files.

## Remote/Local Effects

Declared local state effects only; no implicit publication.

## Errors, Partial, Escalation

Missing or stale context is reported as partial or blocked.

## Unique Constraints

Roadmap output is not a task list or implementation commitment.

## Requirement

### REQ-F-127 - Keep roadmap output non-executing

The skill shall report roadmap context without silently creating work or changing external state.

## Example

`team-roadmap` emits a roadmap view and leaves task creation to an explicit action.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
