# `/spec-manage`

## Purpose

Expose intent-based canonical specification management with optional explicit
mode and scope arguments.

## Triggers and Near-Misses

Routes natural canonical-spec intent and explicit spec modes. Near-misses include
implementation, planning, roadmaps, and user documentation.

## Inputs/Outputs

Arguments may explicitly select mode and scope and are then passed unchanged.
Otherwise the skill selects mode from intent and repository evidence. Output is
canonical specs or read-only audit findings.

## Workflow Stages

Pass explicit arguments unchanged; otherwise infer, inspect, safely disambiguate,
write only in a writing mode, verify, and report.

## Dependencies

`spec-manage`, templates, and repository evidence.

## Remote/Local Effects

Bounded local `specs/` effects only.

## Errors/Partial/Escalation

Conflicts or ambiguous mode selection produce one short question and no writes.

## Unique Constraints

The command does not infer canonical language from the request. It preserves
explicit mode and scope; otherwise the skill selects `spec-init`, `spec-onboard`,
`spec-update`, or read-only `spec-audit` under its evidence and ambiguity rules.

## Requirement

### REQ-I-220 - Route the spec-manage command

The command shall load exactly `spec-manage`, expose the four mode meanings, and
preserve explicit mode, scope, and language boundaries.

## Example

`/spec-manage Document this existing service` selects `spec-onboard` after finding
implementation evidence and no `specs/`; `/spec-manage spec-audit requirements`
passes the explicit read-only mode and scope unchanged.
See [shared concepts](../../architecture/08-crosscutting-concepts/README.md).
