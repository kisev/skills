# `code-explain`

## Purpose

Explain a bounded code range, diff, or walkthrough with evidence coverage.

## Triggers and Near-Misses

Trigger for explanation of code or changes; near-miss: implementation or review.

## Inputs and Outputs

Input is a range, diff, or file. Output is an evidence-linked explanation.

## Workflow Stages

Resolve revision, collect context, explain symbols, mark gaps, report.

## Dependencies

Git and readable repository files.

## Remote/Local Effects

Local reads only; no writes or remote effects.

## Errors, Partial, Escalation

Unreadable files or incomplete ranges produce partial output.

## Unique Constraints

Claims stay bound to the selected revision and coverage boundary.

## Requirement

### REQ-F-104 - Bound explanations to evidence

The skill shall identify the exact code boundary and mark uncovered claims.

## Example

`code-explain` explains a current diff and reports an unreadable untracked file.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
