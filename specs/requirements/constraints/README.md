# Constraint Requirements

### REQ-C-001 - English-only canonical specification

Canonical `specs/` prose shall be English-only, shall contain no `specs/ru`, and
shall not create per-capability contract sidecars beside source files.

### REQ-C-002 - Portable distribution boundary

Supported portable installation automation shall use the configured exact `skills`
CLI version against the GitHub Pages well-known endpoint. User documentation may
follow the stable npm channel. Authored Git sources shall remain deduplicated, while
every published archive is self-contained and requires no OpenCode package.
The OpenCode package shall not invoke the `skills` CLI or inspect its installed
trees and lock files during reconciliation.

### REQ-C-003 - Explicit ownership boundaries

Portable skills, package assets, user configuration, runtime state, and archives
shall have distinct owners; a workflow shall not infer ownership from its caller.
The `skills` CLI owns portable skill installation, update, and removal; the
OpenCode package owns only its integration assets and archive.

### REQ-C-004 - No destructive cleanup

Retired or stale package assets shall not be destructively removed when
content-addressed archival can preserve recovery and auditability.

### REQ-C-005 - Bounded distribution change in this target

The current target changes portable build, publication, and installation transport
without expanding the `27/27/6/3/1` capability inventory or the declared OpenCode
compatibility range.

### REQ-C-006 - Mandatory specification traceability gate

After the bootstrap boundary, behavioral commits shall update the corresponding
canonical `specs/` and traceability evidence or carry the exact
`Spec-Impact: none - <reason>` trailer. The deterministic `task spec:check` gate
is mandatory; semantic `spec-manage` audit remains a separate read-only review.

### REQ-C-007 - Separate version authorities

The project release, portable installer, and OpenCode compatibility range shall
each have one declared authority. Required package, lock, specification, runtime,
and toolchain mirrors shall be checked automatically. User documentation shall
follow stable channels without copying the current project release, and portable
skill metadata shall not carry a version.

### REQ-C-008 - Preserve specification lifecycle history

`spec-manage` shall allocate each new `REQ-*` and `ADR-*` number above the
historical maximum of its namespace without filling gaps or reusing identifiers.
Withdrawn, deprecated, and superseded records shall remain in canonical `specs/`
with enough context to identify the former requirement or decision, its status,
the reason it changed, and its replacement when one exists.
