# Specification audit

Audit is completely read-only. Independently check canonical-document quality, compliance with the language declared in `specs/README.md`, and correspondence to source code, tests, schemas, configuration, CLI/API, CI, and deployment. `specs/` states the claimed contract and repository evidence shows implementation behavior; do not resolve a conflict by silently preferring either. Do not fix anything or create report files. The conversational report may use a different language from the canonical tree.

Treat the bundled validator's result as formal structural evidence only. Its
successful result does not prove semantic quality, that prose follows the
declared language, append-only history without an explicit baseline, or
correspondence with repository behavior. Report `not_checked` for formal scopes
that were not run; do not silently treat them as valid.

A full audit requires one independent critic pass whose initial conclusions are
hidden from the primary reviewer. The primary reviewer accepts or rejects critic
findings against repository evidence.

## Order

1. Determine scope. Without an argument, check the complete canonical `specs/`. With a path, `REQ-*`, `ADR-*`, or described area, check the selected object, related requirements, architecture/ADR, and necessary repository evidence.
2. Check that `specs/README.md` declares one canonical prose language and that the scoped canonical documents follow it. A missing declaration or mixed canonical prose is a quality finding, not permission to modify files.
3. Check internal quality and consistency of requirements, architecture, ADRs, and indexed extensions using the profiles below.
4. Separately check drift between the canonical specification and repository evidence.
5. Report ranked quality findings first, then drift statuses and unchecked boundaries. Do not mix a document defect with a drift status.

At the start, state `Scope: full` or the exact limited scope. For a focused audit, list unchecked boundaries. `OK` is allowed only with explicit `Scope: <scope>`; do not claim project-wide completeness or project-wide `OK`.

## Requirements quality

Check goals and non-scope, terms, inputs and outputs, observable behavior, invariants, edge cases, failure behavior, unsupported behavior, security, compatibility, and verification. Where possible, normative requirements are atomic, unambiguous, necessary, consistent, verifiable, and traceable. Check that each normative fact has exactly one semantic owner: transport-independent behavior in `REQ-F-*`, external surface and protocol semantics in `REQ-I-*`, measurable or verifiable quality in `REQ-Q-*`, and externally imposed solution limits in `REQ-C-*`. Other documents must link rather than repeat the fact. Check that stable `REQ-*` IDs increase above the historical namespace maximum without filling gaps or reuse, inactive IDs use only `deprecated`, `superseded`, or `withdrawn` and retain the required compact `Changed`, `Reason`, and applicable `Replacement` fields and transitions, nontrivial active requirements contain verification, superseded records directly link replacements, machine-readable contracts are referenced, and syntax is not duplicated.

Do not require artificial EARS form or rationale for a trivial requirement. Do not treat an implementation detail as a defect unless it changes an observable contract or architectural invariant.

## Architecture and ADR quality

Check the 12 viewpoints against one another and requirements: system boundary, stakeholders, context, scope; real building-block responsibilities and boundaries; dependency direction, interfaces, ownership, locality; runtime flows, lifecycle, concurrency, failures, recovery; deployment, trust boundaries, security, observability; quality mechanisms; compatibility, migration, testability, risks, debt; feasibility under repository constraints and applicable migration and rollback mechanisms. Material architecture mechanisms must directly link the `REQ-*` entries they provide. Do not require matrices, mapping files, reverse links, or delivery artifacts.

Check security and data ownership without requiring content-free checklists:
context and scope owns trust boundaries and external subjects; deployment owns
runtime boundaries, network exposure, and secret placement; crosscutting concepts
owns identity, authorization, sensitive-data lifecycle, isolation, and
auditability; quality requirements owns measurable security and reliability
properties. Require a brief inapplicability reason only where the concern was
material enough to assess.

An abstraction is justified only by a real responsibility or boundary. Do not present stylistic preference, potential improvement, or unverified future design as a defect. Do not require a diagram when it would not make architecture clearer.

For every ADR, check architectural significance, context, decision drivers, materially different considered options, outcome rationale, positive and negative consequences, status, date, compatibility, migration, rollback, reversibility, risks, direct links to relevant requirements and related ADRs, and supersession. Detailed content is required only for applicable factors; each `Not applicable` statement needs a brief decision-specific reason. Check that ADR numbers increase above the historical maximum without filling gaps or reuse. Do not rewrite or delete an old ADR as though the new decision always existed; replacement requires a new ADR, an explicit reason, links in both directions, and the required compact lifecycle record. Check that ADRs are not used for bugfixes or trivial implementation detail and that significant decisions are not left implicit in architecture prose.

## Quality findings

Report only confirmed problems. Rank them by severity, impact, and uncertainty. For each, state severity, exact path and section or requirement/ADR ID, repository evidence or internal document contradiction, consequence, and minimum canonical-specification fix.

If there are no quality findings, say so explicitly. Do not call missing repository evidence a quality defect when the correct drift status is `SPEC_AHEAD` or `UNKNOWN`.

## Drift statuses

- `OK`: specification is supported by implementation/evidence.
- `SPEC_AHEAD`: specification requires behavior or a property that evidence does not support.
- `IMPLEMENTATION_AHEAD`: implementation has material observable behavior or architectural change absent from canonical specs.
- `CONFLICT`: repository sources contradict each other.
- `UNKNOWN`: reliable automatic verification is impossible; do not guess.

## Drift evidence

For every deviation, state status, requirement ID where present, spec path, source file, symbol/function/class/config path, test/schema/CI evidence, and a short explanation of impact. Do not declare missing mention to be drift without a verifiable observable or architectural consequence.

If drift is absent, report `OK` regardless of quality findings. List material unchecked boundaries as `UNKNOWN`. Output results only in conversation. The user decides whether to change code to match spec or change spec through `spec-update`.
