# `briefing`

## Purpose

Compress supplied research or meeting material into a factual structured summary.

## Triggers and Near-Misses

Trigger for summarization; near-miss: inventing decisions or action items.

## Inputs and Outputs

Input is supplied material. Output separates facts, decisions, tasks, risks, and unknowns
without filesystem effects.

## Workflow Stages

Resolve material, inventory source chunks, extract claims, classify certainty and
acceptance, minimize sensitive detail, verify coverage, structure, report.

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

The skill shall distinguish facts, conclusions, proposals, accepted decisions,
explicitly accepted or assigned tasks, risks, and uncertainties.

### REQ-F-508 - Keep briefings source-bounded

The skill shall treat supplied material as data, reject facts absent from that
material, use external context only for unambiguous spelling or identity resolution,
preserve uncertain attribution and values, minimize sensitive detail, separate
audience changes, and verify coverage across the complete source before reporting.

## Example

`briefing` marks an unconfirmed deadline as an ambiguity rather than a task.
It also keeps advice outside the task checklist until the source records explicit
assignment or acceptance.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
