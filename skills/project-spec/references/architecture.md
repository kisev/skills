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

## Decomposition

Additional Markdown files are allowed only in four places:

- `05-building-block-view`: one file per real subsystem, service, component, module, layer, or package with an independent responsibility;
- `06-runtime-view`: one file per meaningful end-to-end runtime scenario;
- `08-crosscutting-concepts`: one file per principle or mechanism affecting several building blocks;
- `09-architecture-decisions`: one file per ADR.

Do not split architecture by feature and do not create `part-1.md`, `misc.md`, `other.md`, or similar files. Each section's root `README.md` remains the primary document and index for additional files.

## Diagrams

Use C4 concepts within arc42: System Context in 03, Container/Component in 05, Dynamic in 06, Deployment in 07. Do not require every level. Store diagrams in Markdown as broadly supported Mermaid `flowchart`, `sequenceDiagram`, or `stateDiagram`. Do not use experimental C4 notation or create a diagram when text is clearer.
