# Quality Requirements

### REQ-Q-001 - Deterministic verification

The deterministic test and eval suites shall produce stable, structured results
for pass, fail, skipped, error, timeout, malformed, and budget-exceeded cases.

### REQ-Q-002 - Mutation safety

Every package mutation shall validate ownership, scope, confirmation digest, and
freshness before writing, and shall be atomic or recoverable on failure. Preview
receipts shall use a deterministic plan digest plus a unique confirmation digest;
same-scope supersession and one-use confirmation shall fail closed.
Receipts persisted by the previous package patch shall be safely normalized or
replaced during the next preview without weakening integrity validation.

### REQ-Q-003 - Secret safety

Public outputs, reports, archives, and diagnostics shall not disclose credentials
or other secrets, including when inputs are malformed or external calls fail.

### REQ-Q-004 - Evidence completeness

A result shall not be declared complete when required inputs, pages, files,
dependencies, checks, or revision bindings are partial, stale, unknown, or
contradictory.

### REQ-Q-005 - Reproducible distribution

Two builds from one commit and release version shall produce byte-identical
indexes, locks, and archives. Archive URLs shall be content-addressed; build and
deployment checks shall reject undeclared, drifting, unsafe, or digest-mismatched
files.

### REQ-Q-006 - Compatibility preservation

The package shall preserve the declared OpenCode host range and shall fail safely
when host capabilities, configuration, or state are unavailable or malformed.

### REQ-Q-007 - Validate schema contracts

Every committed JSON Schema shall pass its declared meta-schema and validate at
least one concrete contract instance through a standards-compliant validator.
Expressible runtime structure constraints shall remain aligned with the schema
and shall reject the same malformed contract examples.

### REQ-Q-008 - Verify release promotion

Release promotion shall preserve the exact preflighted npm tarball and compare
every deployed Pages file with the release manifest. Registry verification shall
bind npm integrity, signatures, provenance, imports, and CLI behavior to the
release revision before the GitHub Release is created.
