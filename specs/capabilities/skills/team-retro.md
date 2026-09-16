# `team-retro`

## Purpose

Prepare one evidence-based retrospective, delivery review, report, or
presentation against a strict private team profile.

## Triggers and Near-Misses

Trigger for a retrospective action; near-miss: roadmap or sprint planning.

## Inputs and Outputs

Input is the fixed action, an automatically resolved default profile or explicit
context override, an exact period, and bounded evidence. Output is structured
retrospective material plus evidence-completeness and verification results.

## Workflow Stages

Resolve or self-setup the profile, establish `[since, until)`, inventory every
configured project, collect and validate evidence, distinguish delivery states,
draft the configured artifact, write it, verify, and report.

## Dependencies

Shared team profile runtime, optional bounded GitLab metrics collector, declared
evidence connectors, and owned local state.

## Remote/Local Effects

Read-only evidence collection, confirmation-bound local profile writes, and
direct bounded artifact writes. No implicit external publication.

## Errors, Partial, Escalation

Missing profile fields trigger guided self-setup. Partial project, page, signal,
or timestamp evidence remains explicit and prevents a complete claim.

## Unique Constraints

One fixed action is selected; every configured project is accounted for, and
`merged`, `tagged`, and `shipped` are never treated as synonyms.

## Requirement

### REQ-F-126 - Keep retrospective actions explicit

The skill shall execute only the selected fixed action against its declared team context.

## Example

`team-retro` refuses an unknown action before reading or writing state.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
