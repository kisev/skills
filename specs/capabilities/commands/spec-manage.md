# `/spec-manage`

## Purpose

Expose canonical specification management.

## Triggers and Near-Misses

Routes explicit spec modes; near-miss: user docs or code implementation.

## Inputs/Outputs

Arguments select mode and scope; output is specs or audit findings.

## Workflow Stages

Select, pass, inspect, write, verify, report.

## Dependencies

`spec-manage`, templates, and repository evidence.

## Remote/Local Effects

Bounded local `specs/` effects only.

## Errors/Partial/Escalation

Conflicts or ambiguous intent escalate.

## Unique Constraints

The command does not infer canonical language from the request. It passes the
mode and scope to the skill, which selects or preserves the project language
under its mode contract.

## Requirement

### REQ-I-220 - Route the spec-manage command

The command shall load exactly `spec-manage` and preserve mode and language boundaries.

## Example

`/spec-manage` routes `spec-onboard`; the skill obtains the project language
before writing while the conversational response follows the request language.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
