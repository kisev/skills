# `summary`

## Purpose

Compress supplied research or meeting material into a factual structured summary.

## Triggers and Near-Misses

Trigger for summarization; near-miss: inventing decisions or action items.

## Inputs and Outputs

Input is supplied material. Output separates facts, decisions, tasks, risks, and unknowns.

## Workflow Stages

Resolve material, extract claims, classify certainty, structure, report.

## Dependencies

Only supplied source material.

## Remote/Local Effects

No external or repository effects.

## Errors, Partial, Escalation

Missing context is labeled unknown rather than filled by inference.

## Unique Constraints

Exact quotes and technical tokens remain unchanged.

## Requirement

### REQ-F-122 - Separate facts from assumptions

The skill shall distinguish facts, conclusions, decisions, tasks, risks, and uncertainties.

## Example

`summary` marks an unconfirmed deadline as an ambiguity rather than a task.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
