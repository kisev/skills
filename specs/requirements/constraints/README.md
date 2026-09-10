# Constraint Requirements

### REQ-C-001 - English-only canonical specification

Canonical `specs/` prose shall be English-only, shall contain no `specs/ru`, and
shall not create per-capability contract sidecars beside source files.

### REQ-C-002 - Direct Git self-containment

Direct Git distribution shall remain self-contained and shall not require the
OpenCode package at runtime.

### REQ-C-003 - Explicit ownership boundaries

Portable skills, package assets, user configuration, runtime state, and archives
shall have distinct owners; a workflow shall not infer ownership from its caller.

### REQ-C-004 - No destructive cleanup

Retired or stale assets shall not be destructively removed when content-addressed
archival can preserve recovery and auditability.

### REQ-C-005 - No runtime expansion in this target

The canonical target shall describe the current merged behavior without changing
skills, commands, agents, plugins, package tools, eval corpus, or distribution
behavior.

### REQ-C-006 - Mandatory specification traceability gate

After the bootstrap boundary, behavioral commits shall update the corresponding
canonical `specs/` and traceability evidence or carry the exact
`Spec-Impact: none - <reason>` trailer. The deterministic `task spec:check` gate
is mandatory; semantic `spec-manage` audit remains a separate read-only review.
