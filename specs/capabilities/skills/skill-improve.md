# `skill-improve`

- Status: withdrawn
- Status changed: 2026-10-03
- Reason: Replaced by `skill-doctor`, which keeps real-usage experience in
  private XDG diagnoses instead of a static checker cycle.

## Purpose

Historical capability record for the retired skill-quality checker.

## Triggers and Near-Misses

Trigger for skill quality work; near-miss: changing application runtime behavior.

## Inputs and Outputs

Input was one skill path. Output was findings or a bounded improvement with
checks. An optional read-only session report added deterministic usage evidence
from opencode, kilo, and mimo session databases.

## Workflow Stages

Resolve skill, check frontmatter/resources, optionally collect session
evidence, write changes, recheck, report.

## Dependencies

Skill validators, repository rules, and source resources.

## Remote/Local Effects

Local reads and bounded atomic skill writes; no remote effects.

## Errors, Partial, Escalation

Missing resources or validator failures remained explicit.

## Unique Constraints

Portable runtime dependencies and locale contracts cannot be weakened.

## Requirement

### REQ-F-118 - Improve skills without contract drift

Status: withdrawn on 2026-10-03 because the skill was replaced by `skill-doctor`.

Former requirement: the skill shall preserve declared frontmatter, resources,
and portability contracts.

### REQ-F-132 - Ground skill improvements in session evidence

Status: withdrawn on 2026-10-03 because `skill-doctor` owns session evidence
through private incremental diagnoses
([REQ-F-549](skill-doctor.md#req-f-549---keep-current-session-diagnoses-evidence-based-and-incremental)).

Former requirement: the skill shall extract deterministic usage signals from
opencode, kilo, and mimo session databases strictly read-only, and shall keep
verbatim session excerpts out of persisted artifacts.

## Example

`skill-improve` rechecked a skill after adding a missing trigger boundary.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
