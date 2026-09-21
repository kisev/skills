# `spec-manage`

## Purpose

Infer whether to create greenfield specs, describe an existing project, change
the canonical target state, or audit specifications read-only.

## Triggers and Near-Misses

Trigger for canonical project specification work expressed either naturally or
with an explicit mode token. Near-misses include implementation, plans, roadmaps,
and user-facing documentation even when they mention requirements or architecture.

## Inputs and Outputs

Input is intent, repository scope and evidence, with an optional explicit mode.
Output is canonical specs or a read-only audit report. Explicit mode and scope
are preserved without reinterpretation. Audit reports separate formal
validation, quality findings, atomic drift units, unchecked boundaries, critic
results, and a deterministic aggregate result.

## Workflow Stages

Resolve mode from intent and evidence, inspect code, tests, schemas,
configuration, CI, and deployment before distinguishing initialization from
onboarding, classify claims, write bounded specs, run formal validation, perform
semantic review where required, and report checked and `not_checked` scopes.

## Dependencies

Templates, repository evidence, requirements, architecture, ADR rules, and the
bundled Python 3.12+ standard-library-only structural validator.

## Remote/Local Effects

Local reads and bounded atomic `specs/` writes; no remote effects.
The validator itself performs only bounded reads and invokes no Git, network, or
external tools.

## Errors, Partial, Escalation

When several modes remain plausible, one short question distinguishes their
effects and no write occurs before the answer. Audit is always read-only.
Unsafe, missing, non-regular, or non-UTF-8 validator inputs fail as input errors,
not as validation findings. A mandatory failed or unchecked audit step, an
unchecked or `UNKNOWN` in-scope boundary, or an unavailable required critic
produces a partial result without hiding confirmed findings.

## Unique Constraints

Each tree declares one project-selected canonical language independently from
the conversation language. This repository selects English through `REQ-C-001`.
The 19-file skeleton is a minimum; indexed, non-duplicating canonical semantic
sections such as `specs/capabilities/` are allowed.
Each required viewpoint contains a confirmed project fact, a concrete reason for
inapplicability, or an explicitly accepted bounded `UNKNOWN`. Compact examples
illustrate depth only and do not replace templates or semantic readiness.

## Requirement

### REQ-F-120 - Maintain canonical current specifications

The skill shall keep canonical specs evidence-backed, compact, explicit about one
project-selected language, and free of roadmap artifacts while writing only
validated files under `specs/`. It shall distinguish normative intent from
evidence of current behavior according to the selected mode. It shall preserve
explicit mode and scope, otherwise infer mode from intent and repository evidence,
keep read-only intent read-only, and stop without writing when routing is
ambiguous. An audit shall classify atomic claims and boundaries by the first
matching `UNKNOWN`, `CONFLICT`, `SPEC_AHEAD`, `IMPLEMENTATION_AHEAD`, or `OK`
rule; use one severity scale for confirmed defects; preserve separate formal,
quality, drift, boundary, and critic results; and derive `partial`, `findings`,
or `clean` by fixed precedence.

### REQ-F-506 - Validate formal specification invariants

The skill shall run snapshot validation for complete canonical trees and shall
run lifecycle validation only against an explicitly supplied complete baseline.
It shall report unexecuted historical checks as `not_checked` and shall not use a
successful formal result as a substitute for semantic `spec-audit`.

## Example

“Document this existing service as canonical specs” selects `spec-onboard` when
implementation evidence exists and `specs/` does not. “Check the specs without
changing files” selects `spec-audit`.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
