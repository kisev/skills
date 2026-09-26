# `skill-improve`

## Purpose

Check and improve one Agent Skill through a repeatable contract-quality cycle.

## Triggers and Near-Misses

Trigger for skill quality work; near-miss: changing application runtime behavior.

## Inputs and Outputs

Input is one skill path. Output is findings or a bounded improvement with
checks. An optional read-only session report adds deterministic usage evidence
from opencode, kilo, and mimo session databases.

## Workflow Stages

Resolve skill, check frontmatter/resources, optionally collect session
evidence, write changes, recheck, report.

## Dependencies

Skill validators, repository rules, and source resources.

## Remote/Local Effects

Local reads and bounded atomic skill writes; no remote effects.

## Errors, Partial, Escalation

Missing resources or validator failures remain explicit.

## Unique Constraints

Portable runtime dependencies and locale contracts cannot be weakened.

## Requirement

### REQ-F-118 - Improve skills without contract drift

The skill shall preserve declared frontmatter, resources, and portability contracts.

### REQ-F-132 - Ground skill improvements in session evidence

The skill shall extract deterministic usage signals from opencode, kilo, and
mimo session databases strictly read-only, and shall keep verbatim session
excerpts out of persisted artifacts.

#### Verification

Fixture-database tests assert invocation, error, retry, follow-up, and pattern
extraction with read-only access and missing-database error handling.

## Example

`skill-improve` rechecks a skill after adding a missing trigger boundary.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
