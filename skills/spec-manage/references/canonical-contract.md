# Canonical specification contract

This contract defines the language, authority, and extension rules shared by all
`spec-manage` modes. `specs/` describes only the agreed system state after merge.
It does not manage implementation or delivery.

## Canonical language

Each `specs/` tree has exactly one explicitly declared canonical prose language.
Record the declaration in `specs/README.md`. Different projects may choose
different languages. Apply the declared language to all canonical prose,
including requirements, architecture, ADRs, and additional sections. Preserve
identifiers, paths, commands, schema fields, code, quotations, and established
technical terms when translating them would change their meaning.

For deterministic validation in every project language, use the fixed machine
declaration `Canonical language: <non-empty language>.` exactly once. This marker
does not assert that the remaining prose uses the declared language; that is a
semantic `spec-audit` responsibility.

The canonical language is a property of the tree, not of the session. Apply
`references/language-policy.md` independently to conversation, questions, audit
findings, and completion reports. A same-language, different-language, or
mixed-language user request does not override the canonical language.

- In `spec-init` and `spec-onboard`, obtain the user's explicit project-language
  choice before writing and record it in `specs/README.md`.
- In `spec-update`, preserve the declaration in `specs/README.md`. If a legacy
  tree has no declaration, infer its language only when all substantive existing
  canonical prose unambiguously uses one language, then add the declaration. If
  the prose is mixed, absent, or otherwise ambiguous, stop and ask the user.
- In `spec-audit`, check that the declaration exists and that canonical prose
  follows it. Report missing declarations and language violations without
  changing files. The report language may differ from the canonical language.
- Never infer a language migration from the current request. Changing an
  existing tree's language requires an explicit, agreed target state and a
  consistent whole-tree update; otherwise preserve the current language.

## Normative authority by mode

Keep evidence of intent separate from evidence of current behavior. A source can
be authoritative for one claim and non-authoritative for another.

- `spec-init`: confirmed user decisions are normative. Repository material may
  constrain feasibility but does not replace an unconfirmed product or
  architecture decision.
- `spec-onboard`: explicit contract sources and confirmed user decisions are
  normative. An explicit contract source deliberately declares a supported
  interface, policy, invariant, or compatibility commitment. Machine-readable
  schemas and interface declarations are authoritative for their represented
  syntax. Source code, tests, configuration, CI, and deployment prove only
  current behavior unless an explicit contract gives them normative scope.
- `spec-update`: the existing `specs/` tree is the normative baseline. Change it
  only with the agreed target state. Repository behavior can reveal drift or
  feasibility constraints but does not silently replace the baseline.
- `spec-audit`: `specs/` states the claimed contract, while repository evidence
  shows implementation behavior. Report disagreements; do not resolve them by
  silently preferring either side.

When candidate normative sources conflict, show the exact claims and sources and
obtain a user decision in a writing mode. In audit mode, report the conflict and
leave it unresolved.

## Minimum structure and extensions

The 19 `README.md` files represented by `templates/specs/` are the minimum
canonical skeleton, not a closed allowlist. Keep all 19 files, including a brief
inapplicability statement where needed.

An additional section is allowed only when all of these conditions hold:

- it has a stable, named semantic boundary not represented by the minimum
  requirements and architecture sections;
- it contains canonical target-state knowledge, not working material;
- `specs/README.md` indexes it and states its boundary;
- it references, rather than duplicates, normative facts owned elsewhere; and
- it contains no roadmap, task, plan, proposal, delivery status, research,
  analysis, migration log, or implementation artifact.

Additional files inside requirements or architecture must also follow the
decomposition rules in their respective profiles. A `specs/capabilities/`
section is valid when it is an indexed inventory of supported public surfaces
with one clear ownership boundary and references shared requirements and
architecture instead of restating them.

Use the fixed `## Extension Index` heading for deterministic validation. Record
each additional top-level directory exactly once as
`- [Name](name/README.md): Non-empty semantic boundary.` The validator proves
only index correspondence and non-empty boundary text; `spec-audit` determines
whether the boundary is valid and non-duplicating.

If a proposed or existing additional section has no unambiguous canonical
semantic boundary, stop and ask the user in a writing mode; report it as a
finding in audit mode. Never admit process artifacts as an extension.
