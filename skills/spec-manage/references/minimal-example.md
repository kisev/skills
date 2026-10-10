# Compact 19-document example

This fictional `pocket-notes` CLI shows the minimum meaningful depth of a small
specification. It is guidance, not a template: real documents follow their
specialized templates and may need more detail. Each item stands for the
substantive content of one required `README.md`; other document-model details
still apply.

1. `specs/README.md`: Canonical language: English. It defines the supported local `pocket-notes` CLI and indexes only the minimum requirements and architecture sections.
2. `specs/requirements/README.md`: Functional, interface, quality, and constraint owners divide the normative behavior; no extension section exists: the CLI has no additional stable semantic boundary.
3. `specs/requirements/functional/README.md`: `REQ-F-001`: importing a valid note makes it available to later list operations; verification imports one note into an empty store and lists it.
4. `specs/requirements/interfaces/README.md`: `REQ-I-001`: `pocket-notes import <path>` accepts one UTF-8 text-file path; a missing path exits `2` without changing stored notes.
5. `specs/requirements/quality/README.md`: `REQ-Q-001`: listing 10,000 notes from the reference fixture completes within two seconds on the documented runner.
6. `specs/requirements/constraints/README.md`: `REQ-C-001`: the distributed program uses Python 3.12 or later and only its standard library, as the offline distribution environment requires.
7. `specs/architecture/README.md`: The architecture describes one local process and indexes all 12 required viewpoints; no additional viewpoint is justified.
8. `specs/architecture/01-introduction-and-goals/README.md`: One user needs durable personal notes without running a service; shared editing is outside the system boundary.
9. `specs/architecture/02-architecture-constraints/README.md`: No architecture-specific constraint exists beyond `REQ-C-001`: no platform, organization, or topology rule further limits the design.
10. `specs/architecture/03-context-and-scope/README.md`: The user invokes the process and supplies a file; the filesystem is the only external technical subject.
11. `specs/architecture/04-solution-strategy/README.md`: One append-only data file prevents an interrupted import from rewriting previously accepted note records.
12. `specs/architecture/05-building-block-view/README.md`: `CommandParser` validates invocation data and calls `NoteStore`, which alone owns the persisted record format.
13. `specs/architecture/06-runtime-view/README.md`: Import writes one complete record to a temporary file, flushes it, and atomically renames it; failure before rename leaves the active store unchanged.
14. `specs/architecture/07-deployment-view/README.md`: Network deployment is inapplicable because the artifact runs only as a user process without a listening socket.
15. `specs/architecture/08-crosscutting-concepts/README.md`: Store and temporary files use user-only permissions; note text is never written to diagnostic output.
16. `specs/architecture/09-architecture-decisions/README.md`: No ADR exists: the confirmed single-file design has no architecturally significant competing option or compatibility tradeoff.
17. `specs/architecture/10-quality-requirements/README.md`: To provide `REQ-Q-001`, listing streams records and keeps only the current decoded note in memory.
18. `specs/architecture/11-risks-and-technical-debt/README.md`: `UNKNOWN` (accepted by the owner): behavior on filesystem exhaustion. Boundary: import failure recovery only; consequence: no crash consistency is claimed for it. Needed evidence: fault-injection results and an agreed recovery guarantee.
19. `specs/architecture/12-glossary/README.md`: **Active store** is the single data file visible to list operations after a successful atomic rename; temporary files are never active stores.

The example does not authorize empty documents, generic boilerplate, repeated
ownership, or unaccepted `UNKNOWN` boundaries. Do not copy it mechanically.
