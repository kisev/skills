# `spec-manage`

## Purpose

Create, onboard, update, or audit the canonical project specification.

## Triggers and Near-Misses

Trigger for project specification work; near-miss: user-facing documentation or code change.

## Inputs and Outputs

Input is explicit mode and repository scope. Output is canonical specs or read-only findings.

## Workflow Stages

Resolve mode, inspect evidence, classify claims, write bounded specs, verify, report.

## Dependencies

Templates, repository evidence, requirements, architecture, and ADR rules.

## Remote/Local Effects

Local reads and bounded atomic `specs/` writes; no remote effects.

## Errors, Partial, Escalation

Ambiguous intent or conflicting evidence is escalated; audit is read-only.

## Unique Constraints

Each tree declares one project-selected canonical language independently from
the conversation language. This repository selects English through `REQ-C-001`.
The 19-file skeleton is a minimum; indexed, non-duplicating canonical semantic
sections such as `specs/capabilities/` are allowed.

## Requirement

### REQ-F-120 - Maintain canonical current specifications

The skill shall keep canonical specs evidence-backed, compact, explicit about one
project-selected language, and free of roadmap artifacts while writing only
validated files under `specs/`. It shall distinguish normative intent from
evidence of current behavior according to the selected mode.

## Example

`spec-manage` onboards a brownfield repository in its explicitly selected
canonical language and creates only canonical specs.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
