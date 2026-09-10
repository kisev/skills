# `humanize`

## Purpose

Edit Russian prose into natural, direct language without altering exact tokens.

## Triggers and Near-Misses

Trigger for Russian prose editing; near-miss: translation or code editing.

## Inputs and Outputs

Input is prose. Output preserves quotes, code, commands, and identifiers.

## Workflow Stages

Resolve text boundary, identify machine-like phrasing, edit, compare protected tokens, report.

## Dependencies

Input text and language policy.

## Remote/Local Effects

Text-local effects only; no remote effects.

## Errors, Partial, Escalation

Ambiguous language or protected-token conflict is escalated.

## Unique Constraints

Exact quotations and technical tokens are immutable.

## Requirement

### REQ-F-111 - Preserve protected prose tokens

The skill shall humanize prose without changing code, commands, IDs, or exact quotations.

## Example

`humanize` improves a Russian announcement while preserving a command verbatim.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
