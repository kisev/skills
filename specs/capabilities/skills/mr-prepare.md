# `mr-prepare`

## Purpose

Prepare one exact GitLab merge request title, description, and publication plan.

## Triggers and Near-Misses

Trigger for an exact MR URL; near-miss: issue preparation or code review.

## Inputs and Outputs

Input is one MR URL and optional `en`/`ru` locale, defaulting to English.
Output is a stable target-scoped `mr-publication.md`, immutable evidence and
request payloads, and manual `glab` commands beside each proposed metadata edit.

## Workflow Stages

Resolve refs, collect paginated metadata and project MR templates, inspect diff/CI,
preserve verified description information, assess every project label, draft,
finalize, and report in the selected language.

## Dependencies

GitLab read access through `glab`; no local checkout is required.

## Remote/Local Effects

Exact external GET reads and local private artifact; no publication.

## Errors, Partial, Escalation

Core pagination or freshness failure blocks readiness. Missing template access is
reported separately from confirmed absence. Legacy drafts/plans require fresh
preparation. Failed runs never report an older stable document as a new result.

## Unique Constraints

No external mutation is performed. Labels are assessed exhaustively by evidence,
not forced into a single change type. Unresolved labels are preserved. A unique
SemVer compatibility label must agree with the assessed impact.

## Requirement

### REQ-F-114 - Prepare exact merge requests

The skill shall require one exact MR boundary and never publish or mutate GitLab.

It produces a localized metadata-edit TL;DR, proposed values, and explicit-host
manual commands without repeating old descriptions or exposing raw revisions.
Commands consume immutable payloads matching the preview and update labels by
delta. Stable Markdown and its plan pointer are replaced with locking and rollback;
finalize checks their binding and rejects modified or superseded plans.

Project defaults and `.gitlab/merge_request_templates/` are collected at an exact
target-project default-branch revision. Explicit user choice, applicable default,
sole template, then best purpose fit determine selection; material ambiguity is
clarified. Required template structure remains intact. Without a template, keep
a useful existing structure or use Context, Changes, Compatibility and migration,
Verification, and References, omitting inapplicable sections.

Descriptions retain verified purpose, behavior, public interfaces, compatibility,
significant review fixes and actual checks. Private preservation notes explain
meaningful removals/corrections. Pipeline state refers only to the current head.
Unavailable sources and unperformed checks are never presented as verified.

Locale selection follows explicit user request, applicable agent instructions,
session prose, then English. Locale is bound across stages. Runtime labels are
EN/RU; exact commands, identifiers and required template markers are preserved.

## Example

`mr-prepare` refuses a broad project request before API collection.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
