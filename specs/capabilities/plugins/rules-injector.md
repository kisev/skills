# Plugin `rules-injector`

## Purpose

Inject configured repository rules into eligible OpenCode contexts.

## Triggers and Near-Misses

Selectable for rules injection; near-miss: changing source rules or runtime state.

## Inputs/Outputs

Input is plugin options and host context; output is injected context or safe no-op.

## Workflow Stages

Resolve options, inspect scope, inject, preserve boundaries, report.

## Dependencies

Core plugin host and local rules.

## Remote/Local Effects

Reads local rules; no remote effects.

## Errors/Partial/Escalation

Malformed or unavailable rules are reported without guessed injection.

## Unique Constraints

Selectable plugin remains separate from core infrastructure.

## Requirement

### REQ-I-401 - Expose rules-injector safely

The package shall expose `rules-injector` as a selectable plugin without changing core ownership.

## Example

The host selects `rules-injector` for a repository context.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
