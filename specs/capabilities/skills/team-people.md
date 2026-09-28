# `team-people`

## Purpose

Maintain the private people context for one manager: the people profile with
stable facts about reports and stakeholders, the append-only journal of
durable outcomes, and the open-commitment review.

## Triggers and Near-Misses

Trigger for people profile setup, remembered updates, or an open-loop review;
near-miss: preparing a specific 1:1 or drafting feedback.

## Inputs and Outputs

Input is a resolved people profile or setup evidence (notes, protocols,
transcripts, messaging history from exact URLs). Output is a confirmed profile
mutation or bounded journal entries plus an open-commitment summary.

## Workflow Stages

Resolve or self-setup the people profile, classify remembered facts by
durability, route them to the profile or the journal, review open commitments
per person, verify, and report.

## Requirements

### REQ-F-533 - Confirm people profile mutations

Profile mutations shall follow the confirmed prepare-present-confirm-apply
contract with kind `people`. Former identifier: `REQ-TEAM-PEOPLE-01`, normalized
without a behavior change on 2026-09-28.

#### Verification

An unconfirmed profile preview cannot apply; a confirmed matching digest saves
only the selected people profile through the shared profile runner.

### REQ-F-534 - Preserve journal history

The journal shall be append-only; resolutions reference entry IDs and never
rewrite stored entries. Former identifier: `REQ-TEAM-PEOPLE-02`, normalized
without a behavior change on 2026-09-28.

#### Verification

Resolving a commitment appends a resolution referencing its original entry;
the prior journal bytes remain intact.

### REQ-F-535 - Reject credential-like profile fields

Credential-like keys shall be rejected in the people profile. Former identifier:
`REQ-TEAM-PEOPLE-03`, normalized without a behavior change on 2026-09-28.

#### Verification

People-profile validation rejects supplied credential keys before saving any profile.
