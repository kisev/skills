# `/slides-prompts-prepare`

## Purpose

Expose bounded slide prompt preparation.

## Triggers and Near-Misses

Routes prompt work; near-miss: publication.

## Inputs/Outputs

Arguments provide context; output is prompt material.

## Workflow Stages

Select, pass, collect, draft, validate, report.

## Dependencies

`slides-prompts-prepare` and team context.

## Remote/Local Effects

Local plan only; no send.

## Errors/Partial/Escalation

Missing context is partial.

## Unique Constraints

Prompt safety constraints remain unchanged.

## Requirement

### REQ-I-219 - Route the slides prompt command

The command shall load exactly `slides-prompts-prepare` without publication.

## Example

`/slides-prompts-prepare` prepares an illustration prompt.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
