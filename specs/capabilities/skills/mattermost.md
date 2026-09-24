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

Exact external GET reads; local cache may be used; no posts or edits. Channel or
chat intervals wholly older than seven days are intentionally treated as
immutable and reused without freshness expiry. This is a deliberate
performance/freshness tradeoff: it avoids repeated historical API reads, but
late edits or deletes remain stale until an explicit `--refresh`.

## Errors, Partial, Escalation

Auth, pagination, or repeated-page failures produce partial or blocked status.

## Unique Constraints

Origin binding, secret redaction, and one-channel membership boundaries apply.
Unrefreshed stable cache can retain and return content that was later edited or
deleted, including for security or compliance reasons; callers shall use
`--refresh` whenever the current redaction or deletion state matters.

## Requirement

### REQ-F-113 - Read Mattermost safely

The skill shall perform only bounded GET reads and preserve safe evidence on partial failure.

## Example

`mattermost` reads a thread URL and marks an incomplete repeated page as partial.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
