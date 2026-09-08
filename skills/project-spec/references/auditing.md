# Specification audit

Audit is completely read-only. Independently check canonical-document quality and its correspondence to source code, tests, schemas, configuration, CLI/API, CI, and deployment. Do not fix anything or create report files.

## Order

1. Determine scope. Without an argument, check the complete canonical `specs/`. With a path, `REQ-*`, `ADR-*`, or described area, check the selected object, related requirements, architecture/ADR, and necessary repository evidence.
2. Check internal quality and consistency of requirements, architecture, and ADRs using the profiles below.
3. Separately check drift between the canonical specification and repository evidence.
4. Report ranked quality findings first, then drift statuses and unchecked boundaries. Do not mix a document defect with a drift status.

At the start, state `Scope: full` or the exact limited scope. For a focused audit, list unchecked boundaries. `OK` is allowed only with explicit `Scope: <scope>`; do not claim project-wide completeness or project-wide `OK`.

## Requirements quality

Check goals and non-scope, terms, inputs and outputs, observable behavior, invariants, edge cases, failure behavior, unsupported behavior, security, compatibility, and verification. Where possible, normative requirements are atomic, unambiguous, necessary, consistent, verifiable, and traceable. Check stable `REQ-*` IDs, references to machine-readable contracts, and absence of duplicated syntax.

Do not require artificial EARS form or rationale for a trivial requirement. Do not treat an implementation detail as a defect unless it changes an observable contract or architectural invariant.

## Architecture and ADR quality

Check the 12 viewpoints against one another and requirements: system boundary, stakeholders, context, scope; real building-block responsibilities and boundaries; dependency direction, interfaces, ownership, locality; runtime flows, lifecycle, concurrency, failures, recovery; deployment, trust boundaries, security, observability; quality mechanisms; compatibility, migration, testability, risks, debt; feasibility under repository constraints and applicable migration, rollout/rollback mechanisms.

An abstraction is justified only by a real responsibility or boundary. Do not present stylistic preference, potential improvement, or unverified future design as a defect. Do not require a diagram when it would not make architecture clearer.

For every ADR, check architectural significance, context, decision drivers, materially different considered options, outcome rationale, positive and negative consequences, status, date, reversibility, compatibility, risks, linked requirements/ADRs, and supersession. Do not rewrite an old ADR as though the new decision always existed; replacement requires a new ADR and explicit links. Check that ADRs are not used for bugfixes or trivial implementation detail and that significant decisions are not left implicit in architecture prose.

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
