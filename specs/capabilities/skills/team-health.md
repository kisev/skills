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

- REQ-TEAM-HEALTH-01: signals are observations with backing dates; missing
  records are reported missing, never substituted.
- REQ-TEAM-HEALTH-02: surveys are distributed and collected manually; the
  skill never sends or attributes responses.
