# `team-roadmap`

## Purpose

Review or update an evidence-based roadmap from a strict private team profile
without turning it into execution.

## Triggers and Near-Misses

Trigger for roadmap action; near-miss: sprint close or implementation planning.

## Inputs and Outputs

Input is the fixed action, an automatically resolved default profile or explicit
context override, target periods, the current roadmap, and bounded delivery
evidence. Output is a structured roadmap view or confirmation-bound update.

## Workflow Stages

Resolve or self-setup the profile, establish period boundaries, build a
goal-by-goal evidence matrix, reconcile plan and fact, preserve history, assign
every unfinished goal a destination, preview updates, verify, and report.

## Dependencies

Shared team profile runtime, declared evidence connectors, current roadmap and
baseline files, and optional bounded GitLab metrics collection.

## Remote/Local Effects

Read-only evidence collection and confirmation-bound local profile or roadmap
writes; no work-item creation or implicit publication.

## Errors, Partial, Escalation

Missing profile fields trigger guided self-setup. Stale, contradictory, or
partial evidence is attached to affected goals and blocks unsupported claims.

## Unique Constraints

Past plans remain historical under the configured policy, every unfinished goal
has an explicit destination, and roadmap output is not an implementation commitment.

## Requirement

### REQ-F-127 - Keep roadmap output non-executing

The skill shall report roadmap context without silently creating work or changing external state.

## Example

`team-roadmap` emits a roadmap view and leaves task creation to an explicit action.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
