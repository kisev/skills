# Constraint Requirements

### REQ-C-001 - English-only canonical specification

Canonical `specs/` prose shall be English-only, shall contain no `specs/ru`, and
shall not create per-capability contract sidecars beside source files.

### REQ-C-002 - Portable distribution boundary

Supported portable installation shall use pinned `skills@1.5.23` against the
GitHub Pages well-known endpoint. Authored Git sources shall remain deduplicated,
while every published archive is self-contained and requires no OpenCode package.

### REQ-C-003 - Explicit ownership boundaries

Portable skills, package assets, user configuration, runtime state, and archives
shall have distinct owners; a workflow shall not infer ownership from its caller.

### REQ-C-004 - No destructive cleanup

Retired or stale assets shall not be destructively removed when content-addressed
archival can preserve recovery and auditability.

### REQ-C-005 - Bounded distribution change in this target

The `2.2.3` target changes portable build, publication, and installation
transport without expanding the `29/33/6/3/5` capability inventory or the
declared OpenCode compatibility range.

### REQ-C-006 - Mandatory specification traceability gate

After the bootstrap boundary, behavioral commits shall update the corresponding
canonical `specs/` and traceability evidence or carry the exact
`Spec-Impact: none - <reason>` trailer. The deterministic `task spec:check` gate
is mandatory; semantic `spec-manage` audit remains a separate read-only review.
