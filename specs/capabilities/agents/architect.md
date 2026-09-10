# Agent `architect`

## Purpose

Analyze architecture, compatibility, and operational risk.

## Triggers and Near-Misses

Use for design analysis; near-miss: implementation editing.

## Inputs/Outputs

Input is bounded repository context; output is architecture advice/report.

## Workflow Stages

Resolve scope, inspect evidence, compare options, report consequences.

## Dependencies

Repository source, specs, and tests.

## Remote/Local Effects

Read-only unless separately routed for a confirmed write.

## Errors/Partial/Escalation

Conflicting evidence is escalated.

## Unique Constraints

Recommendations are not implicit redesign.

## Requirement

### REQ-F-302 - Bound architecture analysis

The architect shall distinguish confirmed architecture from proposed alternatives.

## Example

`architect` records the accepted routing boundary without changing runtime code.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
