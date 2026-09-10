# `release-prepare`

## Purpose

Prepare a release MR, inventory, SemVer rationale, and announcement plan.

## Triggers and Near-Misses

Trigger for an exact release MR; near-miss: ordinary MR preparation.

## Inputs and Outputs

Input is one exact MR URL and release boundary. Output is a verified plan.

## Workflow Stages

Resolve previous tag, collect range and CI, compute inventory, draft, finalize, report.

## Dependencies

Git, GitLab read access, and repository contracts.

## Remote/Local Effects

Read-only remote collection and local plan artifact; no publish/send effects.

## Errors, Partial, Escalation

Unavailable tags, pagination, or CI freshness are blocking gaps.

## Unique Constraints

Announcement remains separate and illustration prompts contain no logos or text.

## Requirement

### REQ-F-115 - Bound release preparation

The skill shall prepare release evidence without publishing, tagging, or sending announcements.

## Example

`release-prepare` reports the exact base and head SHA before drafting.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
