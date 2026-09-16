# `/doit`

- Status: withdrawn
- Status changed: 2026-09-16
- Reason: The retired `doit` skill no longer has a command adapter.

## Purpose

Historical capability record for the retired command adapter.

## Triggers and Near-Misses

Routes implementation work; near-miss: specification onboarding.

## Inputs/Outputs

Untrusted goal arguments become bounded work input; output is a verified report.

## Workflow Stages

Select, pass, prepare, confirm, execute, verify, report.

## Dependencies

`doit`, native Skill loading, and eligible agents.

## Remote/Local Effects

Effects follow the confirmed skill scope.

## Errors/Partial/Escalation

Failed verification or missing receipt escalates.

## Unique Constraints

The command cannot bypass the execution-card boundary.

## Requirement

### REQ-I-209 - Route the doit command

Status: withdrawn on 2026-09-16 because `/doit` was retired with its skill and
has no replacement.

Former requirement: the command shall load exactly `doit` and preserve bounded
execution and verification.

## Example

`/doit` starts portable coordination for a confirmed change.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
