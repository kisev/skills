# Requirements profile

Use this profile when creating and modifying `specs/requirements/`.

## Requirement quality

Do not claim compliance with ISO/IEC/IEEE 29148. Use it only as a checklist: where possible, a normative requirement is atomic, unambiguous, necessary, consistent, verifiable, and traceable. Describe required behavior, not accidental implementation.

For behavioral requirements, use an EARS-inspired form when it sounds natural:

```text
When <event>,
<system> shall <response>.
```

Do not force every text into this form.

## Identifiers

- `REQ-F-NNN` owns observable behavior independent of a particular transport;
- `REQ-I-NNN` owns an external surface and its protocol semantics;
- `REQ-Q-NNN` owns a measurable or otherwise verifiable quality property;
- `REQ-C-NNN` owns an externally imposed limit on permissible solutions.

One normative fact has exactly one requirement owner. Classify it by what the
fact constrains, not where it was discovered: behavior belongs to `REQ-F-*`,
wire or interaction semantics to `REQ-I-*`, a quality threshold to `REQ-Q-*`,
and an externally imposed solution boundary to `REQ-C-*`. Other requirements
and documents link to that owner instead of restating it. If a fact cannot be
classified unambiguously, stop and ask the user rather than duplicate it.

Treat each identifier namespace as an append-only sequence. A clarification retains its ID, and a move without semantic change does not change its ID. Before assigning a new ID, check canonical documents and available Git history, then choose a number greater than the highest number ever assigned in that namespace. Never fill a gap, renumber an entry, or reuse an ID. If history is unavailable and the historical maximum cannot be determined safely, ask the user.

## Lifecycle history

Active requirements have no required status boilerplate. Do not delete a requirement when its lifecycle status changes or it stops being normative. Keep it under its original heading and ID. Use `deprecated` while it remains supported but is discouraged; it retains its full normative statement and verification. Use `superseded` only when another requirement replaces it and `withdrawn` only when it no longer applies without a replacement.

The allowed transitions are active to `deprecated`, `superseded`, or
`withdrawn`, and `deprecated` to `superseded` or `withdrawn`. `superseded` and
`withdrawn` are terminal. Reintroduction after a terminal state requires a new
ID. Every inactive record has one compact lifecycle line immediately after its
heading:

```markdown
> Lifecycle: `superseded` | Changed: `YYYY-MM-DD` | Reason: <why the normative fact changed> | Replacement: [REQ-F-018](relative/path.md#req-f-018---title)
```

Use exactly `deprecated`, `superseded`, or `withdrawn`. `Changed` and `Reason`
are always required. `Replacement` is required for `superseded`, forbidden for
`withdrawn`, and included for `deprecated` only when a replacement already
exists. The replacement is a direct inline link to its requirement ID.

A superseded or withdrawn entry may be shortened during later consolidation, but it must continue to preserve the ID, former requirement, status-change reason, and replacement link when applicable. Git contains the full edit history; the canonical specification contains the minimum context needed to understand that the requirement existed and why it changed.

Recommended format:

```markdown
### REQ-F-017 - Retrieve job statuses

When a pipeline reaches a terminal state,
the CI checking system shall retrieve the statuses of all expected jobs.

#### Rationale

Add only when it helps understand the requirement.

#### Verification

- Describe observable conditions for successful and failed verification.
```

`Verification` is required for every nontrivial active requirement and describes
observable evidence, not an implementation task. Minimum traceability is direct
and local: an architecture mechanism links the `REQ-*` entries it provides; an
ADR links its relevant requirements and related ADRs; and a superseded record
links its replacement. Do not create traceability matrices, mapping files,
mandatory reverse links, or delivery artifacts.

## Decomposition

- `functional/README.md`: all functional requirements; automatic splitting in v1 is prohibited.
- `interfaces/README.md`: overview and index. An additional file is allowed only for a real external surface: CLI, HTTP API, configuration, events, or another confirmed interface.
- `quality/README.md`: all measurable quality requirements; automatic splitting in v1 is prohibited.
- `constraints/README.md`: all normative constraints; automatic splitting in v1 is prohibited.

One interface file describes one external surface. Do not create future interfaces. Document size alone is not a semantic boundary.

## Machine-readable contracts

Do not completely duplicate OpenAPI, JSON Schema, Protobuf, Helm values schema, typed models, CLI declarations, or package manifests. Reference the formal source of truth and add semantics, compatibility guarantees, errors, and invariants the schema cannot express.
