# `release-review`

## Purpose

Review one release MR for completeness, versioning, compatibility, and readiness.

## Triggers and Near-Misses

Trigger for a release MR review; near-miss: preparing or publishing a release.

## Inputs and Outputs

Input is one exact release MR. Output is ranked findings and readiness status.

## Workflow Stages

Resolve range, inspect inventory/version/CI, check compatibility, report findings.

## Dependencies

Git, GitLab read evidence, package and eval contracts.

## Remote/Local Effects

Read-only local and exact remote reads; no writes.

## Errors, Partial, Escalation

Missing range or fresh pipeline is unknown, not ready.

## Unique Constraints

Release verdict is separate from publication authority.

## Requirement

### REQ-F-116 - Review release readiness

The skill shall require fresh complete evidence before declaring release readiness.

## Example

`release-review` marks a release blocked when a required pipeline is stale.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
