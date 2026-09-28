# `team-agreements`

## Purpose

Capture agreements the moment a conversation ends and keep the
open-commitment list honest.

## Triggers and Near-Misses

Trigger for recording agreements after a call or chat; near-miss: people
profile setup or automated chasing.

## Inputs and Outputs

Input is a stated conversation source and its participants. Output is dated
agreement entries with owners and the open-items review.

## Workflow Stages

Resolve the journal, extract real commitments from the source, record with
owners and dates, review open items, verify.

## Requirements

### REQ-F-523 - Distinguish intentions from commitments

Intentions shall be notes; only owned checkable commitments shall be agreements.
Former identifier: `REQ-TEAM-AGR-01`, normalized without a behavior change on 2026-09-28.

#### Verification

An unowned intention remains a note until an owner and observable commitment exist.

### REQ-F-524 - Keep agreements symmetric

The manager's own promises shall be recorded with the same discipline.
Former identifier: `REQ-TEAM-AGR-02`, normalized without a behavior change on 2026-09-28.

#### Verification

Equivalent manager and report promises produce equivalent ownership and review fields.
