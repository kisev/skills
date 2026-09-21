# Architecture profile

Use arc42 as taxonomy, but do not claim formal compliance with arc42, C4, or ISO. All 12 sections exist from the start.

## Sections

1. `01-introduction-and-goals` - purpose, stakeholders, goals, and requirement overview.
2. `02-architecture-constraints` - architectural consequences of `REQ-C-*`, not a second normative constraint list.
3. `03-context-and-scope` - boundary, users, neighboring systems, external dependencies, and interactions.
4. `04-solution-strategy` - key technologies, decomposition, patterns, and means to meet critical quality goals.
5. `05-building-block-view` - static structure, responsibilities, dependencies, and interfaces.
6. `06-runtime-view` - meaningful end-to-end scenarios, data/control flow, errors, recovery, and asynchronous behavior.
7. `07-deployment-view` - runtime environment, deployment units, infrastructure, network, storage, and relevant CI/CD.
8. `08-crosscutting-concepts` - shared mechanisms: errors, logging, configuration, security, observability, persistence, concurrency, and others.
9. `09-architecture-decisions` - ADR index and ADRs themselves.
10. `10-quality-requirements` - how architecture provides `REQ-Q-*`, not duplication of normative quality requirements.
11. `11-risks-and-technical-debt` - known risks, debt, fragile areas, and expensive changes, but not a backlog.
12. `12-glossary` - ambiguous and project-specific terms, but not a dictionary of common technologies.

Each viewpoint owns only the information named above. Architecture explains
target-state structures and mechanisms and links the requirements they provide;
it does not repeat normative requirement text or describe implementation and
delivery sequencing.

Security and data concerns have explicit owners:

- `03-context-and-scope` owns external subjects, neighboring systems, trust
  boundaries, and exchanges across the system boundary;
- `07-deployment-view` owns runtime boundaries, network exposure, deployed data
  stores, and where secrets are held or injected;
- `08-crosscutting-concepts` owns identity, authorization, sensitive-data
  lifecycle, isolation, and auditability mechanisms;
- `10-quality-requirements` owns the architectural response to measurable
  security and reliability properties in `REQ-Q-*`.

Link between these owners instead of repeating a concern. Record only applicable,
material target-state knowledge; a brief reason is enough when a viewpoint is
inapplicable.

## Decomposition

Within the minimum architecture tree, additional Markdown files are allowed only in four places:

- `05-building-block-view`: one file per real subsystem, service, component, module, layer, or package with an independent responsibility;
- `06-runtime-view`: one file per meaningful end-to-end runtime scenario;
- `08-crosscutting-concepts`: one file per principle or mechanism affecting several building blocks;
- `09-architecture-decisions`: one file per ADR.

Do not split architecture by feature and do not create `part-1.md`, `misc.md`, `other.md`, or similar files. Each section's root `README.md` remains the primary document and index for additional files.

Additional top-level canonical sections are governed by
`references/canonical-contract.md`; they do not weaken these architecture
decomposition rules.

## Diagrams

Use C4 concepts within arc42: System Context in 03, Container/Component in 05, Dynamic in 06, Deployment in 07. Do not require every level. Store diagrams in Markdown as broadly supported Mermaid `flowchart`, `sequenceDiagram`, or `stateDiagram`. Do not use experimental C4 notation or create a diagram when text is clearer.

## Traceability

Every material architecture mechanism directly links the `REQ-*` entries it
provides. A direct link from the dependent statement is sufficient. Do not create
traceability matrices, mapping files, mandatory requirement backlinks, or
delivery artifacts.
