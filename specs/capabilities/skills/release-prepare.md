# `release-prepare`

## Purpose

Prepare one stable release runbook from an exact release MR and inventory.

## Triggers and Near-Misses

Trigger for an exact release MR; near-miss: ordinary MR preparation.

## Inputs and Outputs

Input is one exact MR URL and release boundary. Output is a verified, target-scoped
`release-publication.md` with immutable payloads and manual `glab` commands.

## Workflow Stages

Resolve the boundary, collect exact evidence, decide version, milestone, people,
items, and image style, then draft, finalize, and report. After merge, a read-only
helper refreshes the same runbook with post-merge commands.

## Dependencies

Git, GitLab read access, repository contracts, and user-owned `glab`
authentication for later manual publication.

## Remote/Local Effects

Read-only remote collection and an atomically replaced local runbook backed by
immutable evidence and payloads. The skill and helper execute no remote mutation.

## Errors, Partial, Escalation

Unavailable tags, pagination, exact merge state, CI freshness, component MR
conversations, or required user decisions are blocking gaps. Any changed binding
or payload makes the runbook stale.

## Unique Constraints

One runbook covers pre-merge and post-merge publication. Commands are manual,
immutable, and exactly bound. Release notes equal the MR description byte-for-byte.

## Requirement

### REQ-F-115 - Bound release preparation

The skill shall prepare release evidence and exact manual `glab` commands without
executing them. A complete preparation shall atomically replace one stable
`release-publication.md`; a read-only post-merge helper shall refresh that same
runbook. Incomplete and stale attempts shall not advertise or replace a previous
successful result.

Before merge, the runbook shall cover milestone creation when selected, MR and
milestone update, an announcement comment with the illustration prompt attachment,
and merge. After merge, it shall cover the exact GitLab Release and approved item
comments or closures. Release notes shall be exactly the merged MR description.

Milestone selection shall present an evidence-based recommendation and a custom
option for another existing or new milestone. Description structure precedence shall be current MR, local
project template, then built-in. Image style choices shall be Pixel-art release
quest, Literary world, Neutral abstract systems, and Custom; Literary world shall
require a book or series follow-up, and every prompt shall use one to three
inventory changes.

Contributors shall include every non-merge commit author. Reviewers shall include
approvers and human discussion or note participants across component MRs. Both
lists shall be deduplicated and interactively approved. Work-item candidates shall
remain bounded; every close, comment, or no-action decision shall retain rationale
and uncertainty without asking interactive work-item questions.

## Example

`release-prepare` reports the exact base and head SHA before drafting.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
