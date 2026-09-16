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

Onboarding describes current post-merge state and uses explicit English language selection.

## Requirement

### REQ-F-120 - Maintain canonical current specifications

The skill shall keep canonical specs evidence-backed, compact, language-explicit,
and free of roadmap artifacts while writing only validated files under `specs/`.

## Example

`spec-manage` onboards a brownfield repository in English and creates only canonical specs.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
