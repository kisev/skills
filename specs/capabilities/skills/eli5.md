# `eli5`

## Purpose

Explain one complex concept in plain language for a reader who lacks the
field's background, calibrated to the available knowledge about the reader.

## Triggers and Near-Misses

Trigger for "explain simply" and equivalent requests; near-miss: assuming a
five-year-old audience, or replacing exact conditions with an analogy.

## Inputs and Outputs

Input is the concept and the available context about the reader. Output is a
chat explanation that keeps essential constraints, exceptions, and uncertainty;
no filesystem effects.

## Workflow Stages

Calibrate to the reader, identify the mechanism core, explain with plain words
and glossed terms, preserve constraints and uncertainty, bound analogies,
recheck against the source, report.

## Dependencies

Supplied context and `shared/references/` materialized clarity, language, and
question-guidelines contracts.

## Remote/Local Effects

No external or repository effects.

## Errors, Partial, Escalation

A fact the explanation seems to need but the source lacks stays explicitly
unknown or triggers one bounded question; it is never guessed.

## Unique Constraints

Simplification changes wording only; obligations, confidence, numbers,
exceptions, and boundaries stay exact, and known terms are not re-explained
without reason.

## Requirement

### REQ-F-555 - Explain accessibly without losing constraints or uncertainty

The skill shall calibrate the explanation to the reader's available knowledge,
introduce unavoidable terms with plain glosses, preserve essential
constraints and uncertainty exactly, and treat any analogy as illustrative
only.

#### Verification

Given a technical concept with a performance constraint and an unmeasured
value, the explanation stays accessible to a non-specialist, keeps the
constraint, reports the value as unknown, and invents no numbers.

## Example

`eli5` explains serializable transactions to a colleague without database
experience, keeps the throughput penalty under contention, and leaves the
unmeasured latency impact explicitly unknown.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
