# Plugin `code-simplify`

## Purpose

Inject compact simplification rules into eligible OpenCode contexts.

## Triggers and Near-Misses

Selectable for simplification rule injection; near-miss: changing skill sources
or executing audits is not the wrapper's job.

## Inputs/Outputs

Input is plugin options and host context; output is injected context or safe no-op.

## Workflow Stages

Resolve options, inspect scope, inject, preserve boundaries, report.

## Dependencies

Core plugin host and the shared simplification criteria.

## Remote/Local Effects

Reads local package assets; no remote effects.

## Errors/Partial/Escalation

Malformed or unavailable options are reported without guessed injection.

## Unique Constraints

Selectable plugin remains separate from core infrastructure.

## Requirement

### REQ-I-426 - Expose code-simplify safely

The package shall expose `code-simplify` as a selectable wrapper that injects
compact prevention and audit rules through the session context hook, with the
level selected only through plugin options (`lite`, `full` default, `ultra`;
`off` disables), no new tools, commands, or events, and no mutable
cross-session state.

## Example

The host selects `code-simplify` at the default `full` level for a coding
context.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
