# `/spec-manage`

## Purpose

Expose canonical specification management.

## Triggers and Near-Misses

Routes explicit spec modes; near-miss: user docs or code implementation.

## Inputs/Outputs

Arguments select mode and scope; output is specs or audit findings.

## Workflow Stages

Select, pass, inspect, preview, confirm/apply when applicable, report.

## Dependencies

`spec-manage`, templates, and repository evidence.

## Remote/Local Effects

Confirmed local `specs/` effects only.

## Errors/Partial/Escalation

Conflicts or ambiguous intent escalate.

## Unique Constraints

Onboarding is English-only when explicitly selected here.

## Requirement

### REQ-I-220 - Route the spec-manage command

The command shall load exactly `spec-manage` and preserve mode and language boundaries.

## Example

`/spec-manage` routes `spec-onboard` with English output.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
