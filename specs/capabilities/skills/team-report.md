# `team-report`

## Purpose

Produce the stakeholder-facing periodic roll-up: a quarterly report for
leadership or demo theses.

## Triggers and Near-Misses

Trigger for outward periodic reports; near-miss: the team's own retrospective
(team-retro) or slide imagery.

## Inputs and Outputs

Input is a strict period, delivery evidence, journal facts, and the audience.
Output is a workspace artifact snapshotted in the evidence store.

## Workflow Stages

Establish scope, collect evidence, apply delivery-signal discipline, draft the
roll-up, render and record, verify.

## Requirements

### REQ-F-538 - Exclude private journal content from reports

Stakeholder artifacts shall exclude personal, medical, and financial journal
content. Former identifier: `REQ-TEAM-REPORT-01`, normalized without a behavior
change on 2026-09-28.

#### Verification

An input containing private journal facts produces a stakeholder artifact without them.

### REQ-F-539 - Preserve report evidence completeness

The data-sources section and evidence completeness rules shall follow
[REQ-F-509](team-retro.md#req-f-509---keep-collected-evidence-incremental-and-provenance-bound).
Former identifier: `REQ-TEAM-REPORT-02`, normalized without a behavior change on 2026-09-28.

#### Verification

A report with an unavailable configured source names that boundary and does not
present the missing source as successfully checked.
