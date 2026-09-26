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

- REQ-TEAM-INC-01: human error is analyzed as a condition, never recorded as
  a root cause or conclusion.
- REQ-TEAM-INC-02: unowned or undated actions stay proposed until the user
  decides.
