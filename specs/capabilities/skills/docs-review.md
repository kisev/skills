# `docs-review`

## Purpose

Review user-facing Diataxis documentation for accuracy and usability.

## Triggers and Near-Misses

Trigger for docs review; near-miss: review of canonical `specs/`.

## Inputs and Outputs

Input is a document path or scope. Output is findings only.

## Workflow Stages

Resolve scope, compare sources, inspect links and audience fit, report findings.

## Dependencies

Documentation, source, tests, and links.

## Remote/Local Effects

Local reads only; no writes or remote effects.

## Errors, Partial, Escalation

Missing source evidence is reported as a boundary, not guessed.

## Unique Constraints

Canonical specs are redirected to `spec-manage` audit mode.

## Requirement

### REQ-F-108 - Keep documentation review read-only

The skill shall report documentation findings without changing repository files.

## Example

`docs-review` stops and redirects when the requested path is under `specs/`.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
