# `team-health`

## Purpose

Review team health from recorded signals: cadence adherence,
open-commitment age, feedback balance, and delivery load.

## Triggers and Near-Misses

Trigger for a health review; near-miss: the delivery retrospective or private
per-person diagnostics outside the manager.

## Inputs and Outputs

Input is a strict period, journal signals, profile cadence, and optional
delivery evidence. Output is a manager-view signal table and a stripped
team-view artifact.

## Workflow Stages

Establish scope, load signals, compute per-person and team aggregates, draft
the optional survey, render views, verify limitations.

## Requirements

### REQ-F-527 - Ground health signals

Signals shall be observations with backing dates; missing records shall be
reported missing, never substituted. Former identifier: `REQ-TEAM-HEALTH-01`,
normalized without a behavior change on 2026-09-28.

#### Verification

A sparse evidence window retains missing-data notices and dates for each signal.

### REQ-F-528 - Keep surveys manual

Survey distribution and collection shall remain manual; the skill shall never
send or attribute responses. Former identifier: `REQ-TEAM-HEALTH-02`, normalized
without a behavior change on 2026-09-28.

#### Verification

Survey preparation returns a draft without a send action or invented respondent identity.
