# `asd-ste100`

## Purpose

Check and rewrite technical text in the task's language using Simplified
Technical English principles: one action per instruction, direct wording,
consistent terms, preserved conditions and exceptions.

## Triggers and Near-Misses

Trigger for explicit simplification requests for manuals, procedures, and
safety notes; near-miss: claiming certified ASD-STE100 compliance or forcing
English grammar and word lists onto another language.

## Inputs and Outputs

Input is supplied technical text plus its context. Output is the rewritten
text with an inventory-backed report of preserved obligations, conditions, and
unknowns; no filesystem or external effects.

## Workflow Stages

Read and classify, inventory obligations and conditions, rewrite failing
passages only, mark missing information instead of inventing it, verify
against the inventory, report.

## Dependencies

Supplied text and `shared/references/` materialized clarity, language, and
question-guidelines contracts.

## Remote/Local Effects

No external or repository effects.

## Errors, Partial, Escalation

Missing actor, order, or parameter stays explicitly unknown or triggers one
bounded question; the rewrite never invents it.

## Unique Constraints

The skill follows STE principles without asserting conformance to the official
ASD-STE100 specification; clear text is kept unchanged.

## Requirement

### REQ-F-554 - Preserve meaning while simplifying technical text

The skill shall rewrite only passages that fail the principles, preserve
obligation and permission strength, numbers, conditions, exceptions, actors,
and boundaries, keep already-clear text unchanged, and never present the
result as certified ASD-STE100 text.

#### Verification

Given a wordy instruction with a condition, an exception, and an obligation,
the rewrite keeps all three; given already-clear text, no rewrite is
presented; missing information is marked unknown rather than invented.

## Example

`asd-ste100` keeps the administrator-extended maintenance window exception when
shortening a backup retry instruction, and marks an unnamed service as unknown
instead of choosing one.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
