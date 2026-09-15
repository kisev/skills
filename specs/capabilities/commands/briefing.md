# `/briefing`

## Purpose

Expose factual material summarization.

## Triggers and Near-Misses

Routes supplied notes; near-miss: inventing decisions.

## Inputs/Outputs

Arguments are source material; output separates certainty classes.

## Workflow Stages

Select, pass, extract, classify, structure, report.

## Dependencies

`briefing` only.

## Remote/Local Effects

No external effects.

## Errors/Partial/Escalation

Missing context is labeled unknown.

## Unique Constraints

Protected tokens remain exact.

## Requirement

### REQ-I-222 - Route the briefing command

The command shall load exactly `briefing` and preserve fact/assumption separation.

## Example

`/briefing` structures supplied meeting notes.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
