# `code-review`

## Purpose

Review a local WIP or exact GitLab change for defects and contract regressions.

## Triggers and Near-Misses

Trigger for review; near-miss: preparing a merge request description.

## Inputs and Outputs

Input is an exact scope or WIP. Output is ranked findings with evidence.

## Workflow Stages

Resolve boundary, inspect diff and contracts, critic pass, classify findings, report.

## Dependencies

Git, tests, and optional GitLab read-only evidence.

## Remote/Local Effects

Local reads; external reads only for exact review targets; no writes.

## Errors, Partial, Escalation

Missing head or critic evidence is blocked, not silently ignored.

## Unique Constraints

Findings precede summaries and use exact file/line references.

## Requirement

### REQ-F-105 - Review exact changes

The skill shall review the complete exact diff and rank confirmed risks before summary.

## Example

`code-review` rejects a review when the independent critic receipt is absent.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
