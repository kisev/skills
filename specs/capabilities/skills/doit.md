# `doit`

- Status: withdrawn
- Status changed: 2026-09-16
- Reason: Generic engineering execution is now the responsibility of the host agent and repository guidance.

## Purpose

Historical capability record for the retired generic engineering coordinator.

## Triggers and Near-Misses

Trigger for implementation or repair; near-miss: specification-only onboarding.

## Inputs and Outputs

Input is a concrete engineering goal. Output is a verified change and structured report.

## Workflow Stages

Resolve scope, prepare plan, present, authorize, delegate, verify, report.

## Dependencies

Repository tools, tests, and eligible orchestration agents.

## Remote/Local Effects

Local or external effects require regular Confirmation or an exact action and
boundary frozen in a trusted accepted Goal Mode objective.

## Errors, Partial, Escalation

Failed checks or missing evidence produce structured escalation.

## Unique Constraints

Portable coordinator behavior remains host-neutral; OpenCode routing is an adapter.

## Requirement

### REQ-F-109 - Coordinate bounded changes

Status: withdrawn on 2026-09-16 because the public `doit` skill was retired
without a replacement.

Former requirement: the skill shall execute only regularly confirmed actions or exact actions and
boundaries frozen in a trusted accepted Goal Mode objective identified by immutable
identity, digest, and revision, then verify them before reporting success.

## Example

`doit` dispatches a worker only after regular Confirmation or exact frozen Goal
Mode authorization.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
