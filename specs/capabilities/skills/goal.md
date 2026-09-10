# `goal`

## Purpose

Formulate one verifiable, portable goal as structured Markdown without executing it.

## Triggers and Near-Misses

Trigger for an explicit request to formulate a goal; near-miss: executing or managing one.

## Inputs and Outputs

Input is a request plus available facts and constraints. Output is structured Markdown of at most 4000 characters, normalized internally as `work-item/v1`.

## Workflow Stages

Research facts, ask only material decision questions, optionally run one independent premortem, normalize and validate, present, report.

## Dependencies

Available repository evidence, the bundled work-item contract and validator, and an optional independent premortem agent.

## Remote/Local Effects

Strictly read-only: no file, XDG state, repository, session, receipt, or external-system mutation.

## Errors, Partial, Escalation

Unknown required facts remain open questions and stop conditions; blocking questions prevent a ready result, and oversized goals are split rather than truncated.

## Unique Constraints

The skill does not execute, persist, resume, budget, or automatically continue goals.

## Requirement

### REQ-F-110 - Formulate a read-only goal

The skill shall produce non-empty structured Markdown of at most 4000 characters
from an internally normalized `work-item/v1` and shall not execute, persist,
resume, or automatically continue the goal.

## Example

`goal` turns a repository request into bounded Problem, Outcome, Acceptance criteria, Scope, and Stop conditions sections without creating state.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
