# `docs-prepare`

## Purpose

Prepare one accurate user-facing Diataxis document from verified code evidence.

## Triggers and Near-Misses

Trigger for README/tutorial/reference/how-to work; near-miss: canonical `specs/`.

## Inputs and Outputs

Input is one document path and scope. Output is a draft or confirmed document.

## Workflow Stages

Resolve audience, inspect sources, draft, check links, present, confirm, report.

## Dependencies

Source, tests, and existing documentation.

## Remote/Local Effects

Local reads and confirmed local writes; no remote effects.

## Errors, Partial, Escalation

Unsupported claims are marked or escalated; broken links block completion.

## Unique Constraints

Does not modify `specs/` or invent behavior.

## Requirement

### REQ-F-107 - Prepare factual documentation

The skill shall keep user-facing documentation claims traceable to repository evidence.

## Example

`docs-prepare` updates a package reference without touching canonical specs.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
