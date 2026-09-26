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

- REQ-TEAM-PEOPLE-01: profile mutations follow the confirmed
  prepare-present-confirm-apply contract with kind `people`.
- REQ-TEAM-PEOPLE-02: the journal is append-only; resolutions reference entry
  ids and never rewrite stored entries.
- REQ-TEAM-PEOPLE-03: credential-like keys are rejected in the people profile.
