# `stopit`

## Purpose

Create an anonymized handoff for the next session in a temporary OS directory.

## Triggers and Near-Misses

Trigger when pausing or changing context; near-miss: committing project notes.

## Inputs and Outputs

Input is current session context. Output is a temporary handoff with facts and next step.

## Workflow Stages

Resolve scope, redact, write handoff, verify path, report.

## Dependencies

Current session and temporary directory.

## Remote/Local Effects

Writes only the approved temporary handoff; no repository or remote effects.

## Errors, Partial, Escalation

Redaction uncertainty blocks handoff creation.

## Unique Constraints

Handoff is not a durable repository artifact and must not expose private reasoning.

## Requirement

### REQ-F-121 - Keep handoffs temporary and redacted

The skill shall write only anonymized context to the designated temporary directory.

## Example

`stopit` records a blocker and next step without copying secrets or chain of thought.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
