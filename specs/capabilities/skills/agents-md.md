# `agents-md`

## Purpose

Create or audit scoped `AGENTS.md` instructions from repository evidence.

## Triggers and Near-Misses

Trigger for agent instructions; near-miss: README or contribution documentation.

## Inputs and Outputs

Input is a repository scope. Output is a checked instruction document or audit.

## Workflow Stages

Resolve scope, inspect evidence, prepare content, present, confirm mutation, report.

## Dependencies

Uses repository paths and the shared interaction contract.

## Remote/Local Effects

Local reads; confirmed local writes only. No remote effects.

## Errors, Partial, Escalation

Ambiguous scope is blocked; missing evidence is partial and escalated.

## Unique Constraints

Nested instruction scope and precedence must remain explicit.

## Requirement

### REQ-F-101 - Scope agent instructions

The skill shall create or audit agent instructions only for the resolved repository scope.

## Example

`agents-md` audits the nearest applicable instruction files before editing.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
