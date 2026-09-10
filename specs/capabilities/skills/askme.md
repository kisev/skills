# `askme`

## Purpose

Interview for decisions that determine implementation boundaries.

## Triggers and Near-Misses

Trigger for incomplete requirements; near-miss: a request already fully specified.

## Inputs and Outputs

Input is a goal and repository facts. Output is ordered decision answers.

## Workflow Stages

Resolve dependencies, inspect facts, ask the next independent question, report.

## Dependencies

Repository evidence and user answers.

## Remote/Local Effects

Reads local evidence; no writes or remote effects.

## Errors, Partial, Escalation

Unknown prerequisites block dependent questions; unresolved answers escalate.

## Unique Constraints

Questions follow dependency order and do not repeat answered decisions.

## Requirement

### REQ-F-102 - Ask dependency-bounded questions

The skill shall ask only questions whose answers determine the next safe decision.

## Example

`askme` asks for the exact external boundary before selecting an API workflow.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
