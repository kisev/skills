# Specification audit

Audit is completely read-only. Independently check canonical-document quality,
compliance with the language declared in `specs/README.md`, and correspondence
to source code, tests, schemas, configuration, CLI/API, CI, and deployment.
`specs/` states the claimed contract and repository evidence shows implementation
behavior; do not resolve a conflict by silently preferring either. Do not fix
anything or create report files, temporary audit artifacts, or external
publications.
The conversational report may use a different language from the canonical tree.

Treat the bundled validator's result as formal structural evidence only. Its
successful result does not prove semantic quality, that prose follows the
declared language, append-only history without an explicit baseline, or
correspondence with repository behavior. Report `not_checked` for formal scopes
that were not run; do not silently treat them as valid.

## Scope and evidence snapshot

At the start, state `Scope: full` or the exact limited scope. Without an
argument, check the complete canonical `specs/`. With a path, `REQ-*`, `ADR-*`,
or described area, check the selected object, related requirements,
architecture/ADR, and necessary repository evidence. Bound the repository
paths, symbols, configuration locations, tests, schemas, CI, and deployment
sources that can establish or contradict the scoped claims and boundaries.

Use one bounded evidence snapshot for the audit. Record enough identity to
detect a material change to each read source, using a revision or content digest
when available and otherwise a final bounded reread. If evidence changes during
the audit, rebuild and re-evaluate every affected drift unit against the changed
snapshot or classify it as `UNKNOWN`. Never combine stale and current evidence.
If the scope cannot be bounded or required evidence cannot be read reliably,
continue only far enough to preserve confirmed findings and report
`Overall: partial`.

## Quality review

Check that `specs/README.md` declares one canonical prose language and that the
scoped canonical documents follow it. A missing declaration or mixed canonical
prose is a quality finding, not permission to modify files.

### Requirements quality

Check goals and non-scope, terms, inputs and outputs, observable behavior,
invariants, edge cases, failure behavior, unsupported behavior, security,
compatibility, and verification. Where possible, normative requirements are
atomic, unambiguous, necessary, consistent, verifiable, and traceable. Check
that each normative fact has exactly one semantic owner: transport-independent
behavior in `REQ-F-*`, external surface and protocol semantics in `REQ-I-*`,
measurable or verifiable quality in `REQ-Q-*`, and externally imposed solution
limits in `REQ-C-*`. Other documents must link rather than repeat the fact.
Check that stable `REQ-*` IDs increase above the historical namespace maximum
without filling gaps or reuse, inactive IDs use only `deprecated`,
`superseded`, or `withdrawn` and retain the required compact `Changed`,
`Reason`, and applicable `Replacement` fields and transitions.
Every nontrivial active requirement contains verification. Superseded records directly link
replacements, machine-readable contracts are referenced, and syntax is not
duplicated.

Do not require artificial EARS form or rationale for a trivial requirement. Do
not treat an implementation detail as a defect unless it changes an observable
contract or architectural invariant.

### Architecture and ADR quality

Check the 12 viewpoints against one another and requirements: system boundary,
stakeholders, context, scope; real building-block responsibilities and
boundaries; dependency direction, interfaces, ownership, locality; runtime
flows, lifecycle, concurrency, failures, recovery; deployment, trust
boundaries, security, observability; quality mechanisms; compatibility,
migration, testability, risks, debt; feasibility under repository constraints
and applicable migration and rollback mechanisms. Material architecture
mechanisms must directly link the `REQ-*` entries they provide. Do not require
matrices, mapping files, reverse links, or delivery artifacts.

Check security and data ownership without requiring content-free checklists:
context and scope owns trust boundaries and external subjects; deployment owns
runtime boundaries, network exposure, and secret placement; crosscutting
concepts owns identity, authorization, sensitive-data lifecycle, isolation, and
auditability; quality requirements owns measurable security and reliability
properties. Require a brief inapplicability reason only where the concern was
material enough to assess.

An abstraction is justified only by a real responsibility or boundary. Do not
present stylistic preference, potential improvement, or unverified future design
as a defect. Do not require a diagram when it would not make architecture
clearer.

For every ADR, check architectural significance, context, decision drivers,
materially different considered options, outcome rationale, positive and
negative consequences, status, date, compatibility, migration, rollback,
reversibility, risks, direct links to relevant requirements and related ADRs,
and supersession. Detailed content is required only for applicable factors;
each `Not applicable` statement needs a brief decision-specific reason. Check
that ADR numbers increase above the historical maximum without filling gaps or
reuse. Do not rewrite or delete an old ADR as though the new decision always
existed; replacement requires a new ADR, an explicit reason, links in both
directions, and the required compact lifecycle record. Check that ADRs are not
used for bugfixes or trivial implementation detail and that significant
decisions are not left implicit in architecture prose.

## Severity

Assign exactly one severity to every confirmed quality finding and every
confirmed non-`OK` drift defect. Use the consequence established by evidence,
not the size of the document or implementation change:

- `critical`: confirmed risk of security compromise, irreversible data loss, or
  an unsafe release;
- `high`: substantial defect in an external contract or architectural boundary;
- `medium`: bounded defect in consistency, verifiability, compatibility, or
  recovery;
- `low`: local clarity or traceability problem with no current behavioral
  impact.

`OK` is not a finding. `UNKNOWN` records insufficient comparison evidence, not
a confirmed defect, so it has no severity; state the possible impact and missing
evidence instead. Do not inflate severity because a unit is uncertain.

## Quality findings

Report only confirmed problems. Order findings by `critical`, `high`, `medium`,
then `low`, and use a stable path-and-location order within one severity. For
each, state severity, exact path and section or requirement/ADR ID, repository
evidence or internal document contradiction, consequence, and minimum
canonical-specification fix. If there are no quality findings, say `None`.
Missing repository evidence is not a quality defect when the correct drift
status is `SPEC_AHEAD` or `UNKNOWN`.

## Drift units

Classify one atomic unit at a time:

- a **claim** is one observable behavior or one verifiable property;
- a **boundary** is one interface, ownership, trust, deployment, or dependency
  boundary.

Split a compound statement into separate claims and boundaries before
classification, even when they share one requirement or source location. Give
each unit a stable report-local ID and classify it independently. A unit may
originate in canonical text or in material implementation behavior discovered
inside the scope.

For each unit, apply the first matching row. The rows are ordered and mutually
exclusive:

| Order | Status | Decision |
| - | - | - |
| 1 | `UNKNOWN` | Evidence necessary for comparison is unavailable, stale, changed without successful recheck, or otherwise unreliable. |
| 2 | `CONFLICT` | Reliable in-scope sources assert incompatible states, including a direct contradiction between specification and implementation. |
| 3 | `SPEC_AHEAD` | A canonical claim is not confirmed by implementation evidence, while no contradictory behavior is established. |
| 4 | `IMPLEMENTATION_AHEAD` | Material implementation behavior or an architectural boundary is absent from the canonical specification and does not contradict an existing claim. |
| 5 | `OK` | The claim or boundary is confirmed by reliable evidence. |

Absence of evidence is not automatically `SPEC_AHEAD`: use `UNKNOWN` when the
evidence needed to distinguish missing implementation from an unobserved
implementation is unavailable or unreliable. Use `SPEC_AHEAD` only when the
bounded implementation evidence is sufficient to establish that the canonical
claim is not implemented without establishing contrary behavior.

For every unit, state its ID, type, status, exact spec path and claim/`REQ-*` or
`ADR-*` ID when one exists, implementation path and symbol/function/class/config
location when one exists, related test/schema/CI/deployment evidence, and a
short explanation of impact. For a confirmed non-`OK` defect, also state its
severity. For `UNKNOWN`, state the missing or unreliable evidence. Do not
declare an absent mention to be drift without a verifiable observable or
architectural consequence.

`Drift: OK (<exact scope>; checked: <evidence boundaries>)` is allowed only when
every in-scope drift unit is `OK` and no in-scope boundary is unchecked. Never
emit unqualified `OK`. Quality findings do not change a drift classification;
they change the aggregate result.

## Independent critic

A full audit requires exactly one independent critic. A focused audit does not
require a critic unless the user explicitly requests independent review.
Independence requires a separate agent context or session that has not seen the
primary reviewer's conclusions. A repeated pass in the primary context is not
independent.

Give the critic the exact scope and the same bounded evidence snapshot,
including source identities, but do not give it primary findings, classifications,
severities, or conclusions. The critic performs bounded reads only and returns
either its own candidate findings or an explicit no-findings result. Each
candidate identifies the affected atomic unit or quality location, evidence,
classification, severity when applicable, and impact.

After receiving the critic result, the primary reviewer records exactly one
disposition for every candidate: `accepted`, `rejected`, or `duplicate`.
`accepted` adds or changes a reported finding; `duplicate` identifies the
existing finding or unit; `rejected` explains why the candidate is unsupported
or misclassified. Every disposition includes an evidence-based reason. The
primary reviewer remains responsible for the final classifications.

If a required independent critic cannot be started, cannot access the same
snapshot, or loses independence, continue the primary audit, preserve all
confirmed findings, report `Critic: not_checked` with the reason, and report
`Overall: partial`.

## Aggregate result

Derive the aggregate result after all sections; never use it to remove or
downgrade confirmed findings. Apply the first matching rule:

1. `Overall: partial` if a mandatory check failed or is `not_checked`, an
   in-scope boundary is unchecked or has `UNKNOWN`, or a required critic is
   unavailable or invalid.
2. Otherwise, `Overall: findings` if at least one quality finding exists or at
   least one drift unit is not `OK`.
3. Otherwise, `Overall: clean`.

Mark formal checks as mandatory or not required for this audit before applying
the rule. Full-audit snapshot validation is mandatory. Lifecycle validation is
mandatory only when the audit scope requires a supplied complete baseline; its
ordinary absence is reported as `not_checked (not required)` and does not by
itself make the result partial. Unchecked boundaries outside an explicitly
focused scope remain visible but do not make the focused result partial.

## Conversational report

Use exactly this section order and keep each concern separate:

```text
Scope
Formal validation
Quality findings
Drift
Unchecked boundaries
Critic
Overall
```

In `Scope`, name full or exact focused scope and the bounded evidence snapshot.
In `Formal validation`, list each applicable check and `passed`, `failed`, or
`not_checked`, including whether it was mandatory. In `Quality findings`, write
`None` when empty. In `Drift`, list every atomic unit or the qualified `Drift:
OK (...)` form. In `Unchecked boundaries`, write `None` when empty and identify
whether each listed boundary is in or outside scope. In `Critic`, report
`not_required`, `not_checked`, explicit no-findings, or every candidate and its
disposition. End with exactly one aggregate result. Output the report only in
conversation. The user decides whether to change code to match the specification
or change the specification through a later `spec-update`.
