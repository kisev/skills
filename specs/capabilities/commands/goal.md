# `/goal`

## Purpose

Expose read-only `goal` formulation.

## Triggers and Near-Misses

Route an explicit goal-formulation request; near-miss: execution or lifecycle management.

## Inputs/Outputs

Arguments provide the requested outcome and constraints; output is structured Markdown of at most 4000 characters.

## Workflow Stages

Select, pass untrusted arguments, delegate formulation, present, report.

## Dependencies

The `goal` skill.

## Remote/Local Effects

None; the command does not write or execute the formulated goal.

## Errors/Partial/Escalation

The command preserves open questions, blockers, split requests, and safe escalation.

## Unique Constraints

The command adds no session, budget, persistence, or continuation semantics.

## Requirement

### REQ-I-210 - Route the goal command

The command shall load exactly `goal` and preserve its read-only structured
Markdown limit without adding execution, persistence, or continuation.

## Example

`/goal formulate a verifiable migration objective` returns bounded Markdown without starting work.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
