# Agent `review`

## Purpose

Review a bounded change and return a structured report.

## Triggers and Near-Misses

Use for review; near-miss: implementation.

## Inputs/Outputs

Input is exact diff and requirements; output is findings/report.

## Workflow Stages

Resolve diff, inspect contracts, test, classify findings, report.

## Dependencies

Repository evidence and routing receipt.

## Remote/Local Effects

Read-only review with private report and patch preparation. Explicitly requested
fixing is a separate phase that may change project files.

## Errors/Partial/Escalation

Missing exact diff prevents a complete verdict.

## Unique Constraints

Findings are evidence-first and ranked.

## Requirement

### REQ-F-305 - Produce structured review reports

The review agent shall be available directly and as a manager subagent. It shall
perform the primary review itself and return findings bound to the exact target.
Independent critics shall follow the selected skill's requirements. Review shall
not change project sources or publish; an explicit user request may authorize a
visible transition to a separate fixing phase with bounded changes and checks.
Routed calls return the versioned report; direct use follows the skill's chat contract.

#### Verification

Rendered profiles use `mode: all` and an exact critic allowlist. Nested routing
accepts an independent `review_report` without requiring an implementation card.

## Example

`review` reports a regression with path, selector, and consequence.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
