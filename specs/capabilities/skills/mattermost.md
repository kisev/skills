# `mattermost`

## Purpose

Read a bounded Mattermost post, thread, channel, or chat from an exact URL.

## Triggers and Near-Misses

Trigger for Mattermost reading; near-miss: sending a message or broad search.

## Inputs and Outputs

Input is one exact URL and bounded period/scope. Output is redacted evidence.

## Workflow Stages

Resolve origin, collect GET-only pages, normalize, deduplicate, report completeness.

## Dependencies

Mattermost read API, credentials supplied by the host, and cache policy.

## Remote/Local Effects

Exact external GET reads; local expiring cache may be used; no posts or edits.

## Errors, Partial, Escalation

Auth, pagination, or repeated-page failures produce partial or blocked status.

## Unique Constraints

Origin binding, secret redaction, and one-channel membership boundaries apply.

## Requirement

### REQ-F-113 - Read Mattermost safely

The skill shall perform only bounded GET reads and preserve safe evidence on partial failure.

## Example

`mattermost` reads a thread URL and marks an incomplete repeated page as partial.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
