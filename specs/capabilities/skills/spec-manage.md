# `spec-manage`

## Purpose

Create, onboard, update, or audit the canonical project specification.

## Triggers and Near-Misses

Trigger for project specification work; near-miss: user-facing documentation or code change.

## Inputs and Outputs

Input is explicit mode and repository scope. Output is canonical specs or read-only findings.

## Workflow Stages

Resolve mode, inspect evidence, classify claims, write bounded specs, run formal
validation, perform semantic review where required, and report checked and
`not_checked` scopes.

## Dependencies

Templates, repository evidence, requirements, architecture, ADR rules, and the
bundled Python 3.12+ standard-library-only structural validator.

## Remote/Local Effects

Local reads and bounded atomic `specs/` writes; no remote effects.
The validator itself performs only bounded reads and invokes no Git, network, or
external tools.

## Errors, Partial, Escalation

Ambiguous intent or conflicting evidence is escalated; audit is read-only.
Unsafe, missing, non-regular, or non-UTF-8 validator inputs fail as input errors,
not as validation findings.

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

### REQ-F-506 - Validate formal specification invariants

The skill shall run snapshot validation for complete canonical trees and shall
run lifecycle validation only against an explicitly supplied complete baseline.
It shall report unexecuted historical checks as `not_checked` and shall not use a
successful formal result as a substitute for semantic `spec-audit`.

## Example

`spec-manage` onboards a brownfield repository in its explicitly selected
canonical language and creates only canonical specs.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
