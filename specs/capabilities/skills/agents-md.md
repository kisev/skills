# `agents-md`

## Purpose

Create or audit scoped `AGENTS.md` instructions from repository evidence.

## Triggers and Near-Misses

Trigger for agent instructions; near-miss: README or contribution documentation.

## Inputs and Outputs

Input is a repository scope. Output is a checked instruction document or audit.

## Workflow Stages

Resolve scope, inspect evidence, prepare content, write, validate, report.

## Dependencies

Uses repository paths and the shared interaction contract.

## Remote/Local Effects

Local checkout reads, or exact-revision remote reads when no checkout is
available; bounded atomic local writes only. No remote mutations.

## Errors, Partial, Escalation

Ambiguous scope is blocked; missing evidence is partial and escalated.

## Unique Constraints

Nested instruction scope and precedence must remain explicit. A local checkout,
including uncommitted changes, remains the source of truth when available.

## Requirement

### REQ-F-101 - Scope agent instructions

The skill shall create or audit agent instructions only for the resolved repository scope.

## Example

`agents-md` audits the nearest applicable instruction files before editing.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
