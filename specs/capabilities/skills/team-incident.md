# `team-incident`

## Purpose

Facilitate one blameless postmortem from supplied materials into a timeline,
contributing factors, and owned action items.

## Triggers and Near-Misses

Trigger for postmortem facilitation; near-miss: live incident response or
public status communication.

## Inputs and Outputs

Input is the incident window and user-supplied materials. Output is a
workspace postmortem document and recorded action-item agreements.

## Workflow Stages

Establish the incident, load contexts, build the sourced timeline, analyze
contributing factors, define owned actions, write and verify.

## Requirements

### REQ-F-529 - Analyze conditions behind human error

Human error shall be analyzed as a condition, never recorded as a root cause
or conclusion. Former identifier: `REQ-TEAM-INC-01`, normalized without a
behavior change on 2026-09-28.

#### Verification

A supplied operator mistake leads to examination of contributing conditions,
not a blame-based root-cause conclusion.

### REQ-F-530 - Keep undecided incident actions proposed

Unowned or undated actions shall remain proposed until the user decides.
Former identifier: `REQ-TEAM-INC-02`, normalized without a behavior change on 2026-09-28.

#### Verification

Missing ownership or dates are visible and never silently filled in the final actions.
