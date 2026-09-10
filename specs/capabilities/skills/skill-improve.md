# `skill-improve`

## Purpose

Check and improve one Agent Skill through a repeatable contract-quality cycle.

## Triggers and Near-Misses

Trigger for skill quality work; near-miss: changing application runtime behavior.

## Inputs and Outputs

Input is one skill path. Output is findings or a bounded improvement with checks.

## Workflow Stages

Resolve skill, check frontmatter/resources, preview changes, apply, recheck, report.

## Dependencies

Skill validators, repository rules, and source resources.

## Remote/Local Effects

Local reads and confirmed skill writes; no remote effects.

## Errors, Partial, Escalation

Missing resources or validator failures remain explicit.

## Unique Constraints

Portable runtime dependencies and locale contracts cannot be weakened.

## Requirement

### REQ-F-118 - Improve skills without contract drift

The skill shall preserve declared frontmatter, resources, and portability contracts.

## Example

`skill-improve` rechecks a skill after adding a missing trigger boundary.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
