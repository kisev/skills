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

- `REQ-F-NNN` - functional requirement;
- `REQ-I-NNN` - interface requirement;
- `REQ-Q-NNN` - quality requirement;
- `REQ-C-NNN` - constraint.

Do not renumber or reuse existing IDs. A clarification retains its ID, a removed ID remains reserved, and a move without semantic change does not change its ID. Before assigning a new ID, check canonical documents and available Git history, then choose the next never-used number. If history is unavailable and a safe number cannot be determined, ask the user.

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

`Verification` is required when the verification method is not trivial.

## Decomposition

- `functional/README.md`: all functional requirements; automatic splitting in v1 is prohibited.
- `interfaces/README.md`: overview and index. An additional file is allowed only for a real external surface: CLI, HTTP API, configuration, events, or another confirmed interface.
- `quality/README.md`: all measurable quality requirements; automatic splitting in v1 is prohibited.
- `constraints/README.md`: all normative constraints; automatic splitting in v1 is prohibited.

One interface file describes one external surface. Do not create future interfaces. Document size alone is not a semantic boundary.

## Machine-readable contracts

Do not completely duplicate OpenAPI, JSON Schema, Protobuf, Helm values schema, typed models, CLI declarations, or package manifests. Reference the formal source of truth and add semantics, compatibility guarantees, errors, and invariants the schema cannot express.
