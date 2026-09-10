# `/team-roadmap`

## Purpose

Expose non-executing roadmap views.

## Triggers and Near-Misses

Routes roadmap action; near-miss: task creation.

## Inputs/Outputs

Arguments select context/action; output is a roadmap view.

## Workflow Stages

Select, pass, inspect, render, report.

## Dependencies

`team-roadmap` shared runtime.

## Remote/Local Effects

Declared local effects only.

## Errors/Partial/Escalation

Stale context is explicit.

## Unique Constraints

No implicit task creation.

## Requirement

### REQ-I-227 - Route the team-roadmap command

The command shall load exactly `team-roadmap` without creating work.

## Example

`/team-roadmap` renders the current roadmap context.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
