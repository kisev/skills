# Requirements profile

## Requirement quality

Do not claim ISO/IEC/IEEE 29148 compliance; use it only as a checklist. Where
possible, a normative requirement is atomic, unambiguous, necessary, consistent,
verifiable, and traceable. Describe required behavior, not accidental
implementation.

For behavioral requirements, use an EARS-inspired form when it sounds natural:

```text
When <event>,
<system> shall <response>.
```

## Identifiers

- `REQ-F-NNN` owns observable behavior independent of a particular transport;
- `REQ-I-NNN` owns an external surface and its protocol semantics;
- `REQ-Q-NNN` owns a measurable or otherwise verifiable quality property;
- `REQ-C-NNN` owns an externally imposed limit on permissible solutions.

One normative fact has exactly one owner (`REQ-F-*`, `REQ-I-*`, `REQ-Q-*`,
`REQ-C-*`), classified by what it constrains, not where it was discovered.
Other requirements and documents link to it, not restate it. If classification
is ambiguous, stop and ask rather than duplicate it.

Treat each identifier namespace as an append-only sequence. A clarification retains its ID, and a move without semantic change does not change its ID. Before assigning a new ID, check canonical documents and available Git history, then choose a number greater than the highest number ever assigned in that namespace. Never fill a gap, renumber an entry, or reuse an ID. If history is unavailable and the historical maximum cannot be determined safely, ask the user.

## Lifecycle history

Active requirements need no status boilerplate. Do not delete a requirement when its lifecycle status changes or it stops being normative; keep it under
its original heading and ID. Use `deprecated` while supported but discouraged;
it keeps its full normative statement and verification. Use `superseded` only
when another requirement replaces it; `withdrawn` only when it no longer
applies without a replacement.

Allowed transitions: active to `deprecated`/`superseded`/`withdrawn`;
`deprecated` to `superseded`/`withdrawn`. `superseded` and `withdrawn` are
terminal; reintroduction needs a new ID. One compact lifecycle line
immediately after each inactive record's heading:

```markdown
> Lifecycle: `superseded` | Changed: `YYYY-MM-DD` | Reason: <why the normative fact changed> | Replacement: [REQ-F-018](relative/path.md#req-f-018---title)
```

Use exactly `deprecated`, `superseded`, or `withdrawn`. `Changed` and `Reason`
are always required. `Replacement` is required for `superseded`, forbidden for
`withdrawn`, and included for `deprecated` only when a replacement already
exists. The replacement links directly inline to its requirement ID.

A superseded or withdrawn entry may be shortened, but must still preserve the ID, former requirement, status-change reason, and replacement link when
applicable.

Recommended format:

```markdown
### REQ-F-017 - Retrieve job statuses

When a pipeline reaches a terminal state,
the CI checking system shall retrieve the statuses of all expected jobs.

#### Rationale

Only when it helps understanding.

#### Verification

- Describe observable conditions for successful and failed verification.
```

Every nontrivial active requirement requires `Verification`, describing
observable evidence, not implementation tasks. Minimum traceability is direct
and local: an architecture mechanism links the `REQ-*` entries it provides; an
ADR links its relevant requirements and related ADRs; a superseded record links its
replacement. Do not create traceability matrices, mapping files, mandatory
reverse links, or delivery artifacts.

## Decomposition

- `functional/README.md`: all functional requirements; automatic splitting in v1 is prohibited.
- `interfaces/README.md`: overview and index. An additional file is allowed only for a real external surface: CLI, HTTP API, configuration, events, or another confirmed interface.
- `quality/README.md`: all measurable quality requirements; automatic splitting in v1 is prohibited.
- `constraints/README.md`: all normative constraints; automatic splitting in v1 is prohibited.

One interface file per external surface; do not create future interfaces.
Document size alone is not a semantic boundary.

## Machine-readable contracts

Do not completely duplicate OpenAPI, JSON Schema, Protobuf, Helm values schema,
typed models, CLI declarations, or package manifests. Reference the formal
source of truth and add semantics, compatibility guarantees, errors, and
invariants the schema cannot express.
