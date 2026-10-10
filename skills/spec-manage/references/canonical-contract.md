# Canonical specification contract

`specs/` describes only the agreed system state after merge, not implementation
or delivery.

## Canonical language

Each `specs/` tree has exactly one explicitly declared canonical prose language,
recorded in `specs/README.md`; different projects may choose different
languages. Apply it to all canonical prose, including requirements,
architecture, ADRs, and additional sections. Preserve identifiers, paths,
commands, schema fields, code, quotations, and established technical terms
where translation would change their meaning.

Use the fixed machine declaration `Canonical language: <non-empty language>.`
exactly once. The marker does not assert the prose follows it; that is
`spec-review`'s semantic check. Apply `references/language-policy.md`
independently to conversation, questions, audit findings, and completion
reports. A same-language, different-language, or
mixed-language user request does not override the canonical language.

- In `spec-init` and `spec-onboard`, obtain the user's explicit project-language choice before writing and record it in `specs/README.md`.
- In `spec-update`, preserve the declaration. If a legacy tree lacks one, infer its language only when all substantive existing canonical prose unambiguously uses one language, then add it. If the prose is mixed, absent, or otherwise ambiguous, stop and ask.
- In `spec-review`, check the declaration exists and the prose follows it. Report missing declarations and violations without changing files; the report language may differ from the canonical language.
- Never infer a language migration from the current request. Changing an existing tree's language requires an explicit, agreed target state and a consistent whole-tree update; otherwise preserve the current language.

## Normative authority by mode

- `spec-init`: confirmed user decisions are normative. Repository material does not replace an unconfirmed product or architecture decision.
- `spec-onboard`: explicit contract sources and confirmed user decisions are normative. An explicit contract source declares a supported interface, policy, invariant, or compatibility commitment; machine-readable schemas and interface declarations are authoritative for their syntax. Source code, tests, configuration, CI, and deployment prove only current behavior unless an explicit contract gives them normative scope.
- `spec-update`: the existing `specs/` tree is the normative baseline. Change it only with the agreed target state; repository behavior never silently replaces the baseline.
- `spec-review`: `specs/` states the claimed contract; repository evidence shows implementation behavior. Report disagreements; do not resolve them by silently preferring either side.

When candidate normative sources conflict, show the claims and sources and
obtain a user decision in a writing mode. In audit mode, report the conflict and
leave it unresolved.

## Minimum structure and extensions

The 19 `README.md` files represented by `templates/specs/` are the minimum
canonical skeleton, not a closed allowlist. Keep all 19 files, each viewpoint
holding a brief project-specific fact, concrete inapplicability reason, or
explicitly accepted bounded `UNKNOWN`. Apply `references/content-states.md`; do
not use those forms as automatic placeholders or to weaken semantic readiness or
audit criteria.

An additional section is allowed only when all of these conditions hold:

- a stable, named semantic boundary not represented by the minimum requirements and architecture sections;
- canonical target-state knowledge, not working material;
- a `specs/README.md` index entry stating its boundary;
- references to, not duplication of, normative facts owned elsewhere; and
- no roadmap, task, plan, proposal, delivery status, research, analysis, migration log, or implementation artifact.

Additional requirements or architecture files must also follow those profiles'
decomposition rules. A `specs/capabilities/` section is valid when it
is an indexed inventory of supported public surfaces with one clear ownership
boundary, referencing shared requirements and architecture, not restating them.

Use the fixed `## Extension Index` heading. Record each additional top-level
directory exactly once as
`- [Name](name/README.md): Non-empty semantic boundary.` The validator proves
only index correspondence and non-empty boundary text; `spec-review` judges
validity and non-duplication.

If a proposed or existing additional section has no unambiguous canonical
semantic boundary, stop and ask the user in a writing mode; report it as a
finding in audit mode. Never admit process artifacts as an extension.
