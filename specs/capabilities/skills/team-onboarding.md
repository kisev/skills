# `team-onboarding`

## Purpose

Assemble an onboarding pack and first-weeks plan for one new team member from
the delivery and people contexts.

## Triggers and Near-Misses

Trigger for onboarding preparation; near-miss: account provisioning or running
the first 1:1.

## Inputs and Outputs

Input is the new member's facts and both profile kinds. Output is a workspace
artifact plus a journal note.

## Workflow Stages

Establish scope, load both contexts, build the pack and dated plan, write and
record, verify unconfirmed items.

## Requirements

### REQ-F-531 - Exclude private people context from onboarding

Private fields of existing reports, including cautions, growth areas, and
journal entries, shall never enter the pack. Former identifier: `REQ-TEAM-ONB-01`,
normalized without a behavior change on 2026-09-28.

#### Verification

A profile containing private cautions produces a newcomer pack without those fields.

### REQ-F-532 - Mark unconfirmed onboarding information

Items the profiles cannot confirm shall be marked for verification instead of
invented. Former identifier: `REQ-TEAM-ONB-02`, normalized without a behavior
change on 2026-09-28.

#### Verification

Missing access instructions remain explicit verification items, not invented commands.
