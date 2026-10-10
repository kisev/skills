# Specification review

Review never edits the reviewed project. Independently check canonical-document quality, compliance with the language declared in `specs/README.md`, and correspondence to source code, tests, schemas, configuration, CLI/API, CI, and deployment; never silently prefer either side of a `specs/`-versus-repository conflict. Private evidence follows `references/documentation-review.md` (full, incremental, unchanged modes). A repeated invocation reuses decisions and checks affected dependencies. The conversational report may use a different language from the canonical tree.

The bundled validator's result is formal structural evidence only: success proves neither semantic quality, declared-language prose, append-only history without an explicit baseline, nor repository correspondence. Report `not_checked` for unrun formal scopes, never treating them as valid.

## Scope and evidence snapshot

State `Scope: full` or the exact limited scope at the start. No argument: check the complete canonical `specs/`. A path, `REQ-*`, `ADR-*`, or described area: check the selected object, related requirements, architecture/ADR, and necessary repository evidence. Bound the repository paths, symbols, configuration, tests, schemas, CI, and deployment sources able to establish or contradict the scoped claims and boundaries.

Use one bounded evidence snapshot; record enough identity per read source to detect material change — a revision or content digest when available, else a final bounded reread. Changed evidence: rebuild and re-evaluate every affected drift unit against it or classify it `UNKNOWN`; never combine stale and current evidence. If the scope cannot be bounded or required evidence cannot be read reliably, continue only far enough to preserve confirmed findings and report `Overall: partial`.

## Quality review

`specs/README.md` must declare one canonical prose language and scoped canonical documents must follow it; a missing declaration or mixed prose is a quality finding, not permission to modify files.

### Requirements quality

Check goals and non-scope, terms, inputs and outputs, observable behavior, invariants, edge cases, failure behavior, unsupported behavior, security, compatibility, and verification; where possible, normative requirements are atomic, unambiguous, necessary, consistent, verifiable, and traceable. Each normative fact must have exactly one semantic owner: transport-independent behavior in `REQ-F-*`, external surface and protocol semantics in `REQ-I-*`, measurable or verifiable quality in `REQ-Q-*`, externally imposed solution limits in `REQ-C-*`; other documents link rather than repeat it. Stable `REQ-*` IDs must increase above the historical namespace maximum without filling gaps or reuse; inactive IDs use only `deprecated`, `superseded`, or `withdrawn` and retain the required compact `Changed`, `Reason`, and applicable `Replacement` fields and transitions. Every nontrivial active requirement contains verification. Superseded records directly link replacements, machine-readable contracts are referenced, and syntax is not duplicated.

Do not require artificial EARS form or rationale for a trivial requirement; an implementation detail is a defect only when it changes an observable contract or architectural invariant.

### Architecture and ADR quality

Check the 12 viewpoints against one another and requirements: system boundary, stakeholders, context, scope; building-block responsibilities and boundaries; dependency direction, interfaces, ownership, locality; runtime flows, lifecycle, concurrency, failures, recovery; deployment, trust boundaries, security, observability; quality mechanisms; compatibility, migration, testability, risks, debt; feasibility under repository constraints and applicable migration and rollback mechanisms. Material architecture mechanisms must directly link the `REQ-*` entries they provide; do not require matrices, mapping files, reverse links, or delivery artifacts.

Check security and data ownership without requiring content-free checklists: context and scope owns trust boundaries and external subjects; deployment owns runtime boundaries, network exposure, and secret placement; crosscutting concepts owns identity, authorization, sensitive-data lifecycle, isolation, and auditability; quality requirements owns measurable security and reliability properties. Require a brief inapplicability reason only for material concerns.

An abstraction is justified only by a real responsibility or boundary; stylistic preference, potential improvement, or unverified future design is not a defect, and a diagram is required only when it clarifies architecture.

Check every ADR for architectural significance, context, decision drivers, materially different considered options, outcome rationale, positive and negative consequences, status, date, compatibility, migration, rollback, reversibility, risks, links to relevant requirements and related ADRs, and supersession; detailed content is required only for applicable factors, and each `Not applicable` needs a brief decision-specific reason. ADR numbers must increase above the historical maximum without filling gaps or reuse. Do not rewrite or delete an old ADR as though the new decision always existed; replacement requires a new ADR, an explicit reason, links in both directions, and the required compact lifecycle record. ADRs must not record bugfixes or trivial implementation detail; significant decisions must not stay implicit in architecture prose.

## Severity

Assign exactly one severity to every confirmed quality finding and every confirmed non-`OK` drift defect, by evidenced consequence, not by document or implementation-change size:

- `critical`: confirmed risk of security compromise, irreversible data loss, or an unsafe release;
- `high`: substantial defect in an external contract or architectural boundary;
- `medium`: bounded defect in consistency, verifiability, compatibility, or recovery;
- `low`: local clarity or traceability problem with no current behavioral impact.

`UNKNOWN` records insufficient comparison evidence, not a confirmed defect, so it has no severity.

## Quality findings

Report only confirmed problems. Order findings by `critical`, `high`, `medium`, then `low`, in stable path-and-location order within a severity. For each, state severity, exact path and section or requirement/ADR ID, repository evidence or internal document contradiction, consequence, and minimum canonical-specification fix.

## Drift units

Classify one atomic unit at a time:

- a **claim** is one observable behavior or one verifiable property;
- a **boundary** is one interface, ownership, trust, deployment, or dependency boundary.

Split compound statements into separate claims and boundaries before classification, even within one requirement or source location; give each unit a stable report-local ID.

For each unit, apply the first matching row; the rows are ordered and mutually exclusive:

| Order | Status | Decision |
| - | - | - |
| 1 | `UNKNOWN` | Evidence necessary for comparison is unavailable, stale, changed without successful recheck, or otherwise unreliable. |
| 2 | `CONFLICT` | Reliable in-scope sources assert incompatible states, including a direct contradiction between specification and implementation. |
| 3 | `SPEC_AHEAD` | A canonical claim is not confirmed by implementation evidence, while no contradictory behavior is established. |
| 4 | `IMPLEMENTATION_AHEAD` | Material implementation behavior or an architectural boundary is absent from the canonical specification and does not contradict an existing claim. |
| 5 | `OK` | The claim or boundary is confirmed by reliable evidence. |

Absence of evidence is `UNKNOWN`, not `SPEC_AHEAD`, when the evidence needed to distinguish a missing from an unobserved implementation is unavailable or unreliable.

For each unit, state its ID, type, status, exact spec path and claim/`REQ-*` or `ADR-*` ID if any, implementation path and symbol/function/class/config location if any, related test/schema/CI/deployment evidence, and a short impact note; for a confirmed non-`OK` defect, also its severity; for `UNKNOWN`, the missing or unreliable evidence.

`Drift: OK (<exact scope>; checked: <evidence boundaries>)` is allowed only when every in-scope drift unit is `OK` and no in-scope boundary is unchecked. Never emit unqualified `OK`. Quality findings do not change a drift classification; they change the aggregate result.

## Independent critic

A full audit requires exactly one independent critic; a focused audit does not, unless the user explicitly requests independent review. Independence requires a separate agent context or session that has not seen the primary reviewer's conclusions.

Give the critic the exact scope, the same bounded evidence snapshot including source identities, and no primary findings, classifications, severities, or conclusions. The critic performs bounded reads only, returning candidate findings or an explicit no-findings result; each candidate identifies the affected unit or quality location, evidence, classification, severity when applicable, and impact.

The primary reviewer records exactly one disposition for every candidate: `accepted`, `rejected`, or `duplicate`. `accepted` adds or changes a reported finding; `duplicate` identifies the existing finding or unit; `rejected` explains why the candidate is unsupported or misclassified. Every disposition includes an evidence-based reason.

If a required independent critic cannot be started, cannot access the same snapshot, or loses independence, continue the primary audit, preserve all confirmed findings, and report `Critic: not_checked` with the reason.

## Aggregate result

Derive the aggregate result after all sections; never use it to remove or downgrade confirmed findings. First matching rule:

1. `Overall: partial` if a mandatory check failed or is `not_checked`, an in-scope boundary is unchecked or has `UNKNOWN`, or a required critic is unavailable or invalid.
2. Otherwise, `Overall: findings` if at least one quality finding exists or at least one drift unit is not `OK`.
3. Otherwise, `Overall: clean`.

Before applying the rule, mark each formal check mandatory or not required for this audit; full-audit snapshot validation is mandatory. Lifecycle validation is mandatory only when the scope requires a supplied complete baseline; report its ordinary absence as `not_checked (not required)`.

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

In `Formal validation`, list each applicable check and `passed`, `failed`, or `not_checked`, marked mandatory or not. In `Quality findings`, write `None` when empty. In `Unchecked boundaries`, write `None` when empty and mark each listed boundary in or outside scope. In `Critic`, report `not_required`, `not_checked`, explicit no-findings, or every candidate and its disposition. Output the report only in conversation; the user decides whether to change code to match the specification or change the specification via a later `spec-update`.
