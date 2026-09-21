# Quality Requirements View

Determinism comes from pinned dependencies, stable selectors, content digests,
hostless evals, standards-compliant schema validation with concrete instances,
generated-asset parity, and release tag/version/revision/artifact checks.
Hostless contract validation is explicitly separated from trusted-live
per-case observations; sandbox diffs enforce supported mutation boundaries.
Safety comes from deterministic project/global scope, archive digest verification, ownership, one-use
confirmation/receipts, secret redaction, and atomic rollback.
These mechanisms provide
[REQ-Q-001](../../requirements/quality/README.md#req-q-001---deterministic-verification),
[REQ-Q-002](../../requirements/quality/README.md#req-q-002---mutation-safety),
[REQ-Q-003](../../requirements/quality/README.md#req-q-003---secret-safety),
[REQ-Q-004](../../requirements/quality/README.md#req-q-004---evidence-completeness),
[REQ-Q-005](../../requirements/quality/README.md#req-q-005---reproducible-distribution),
and [REQ-Q-008](../../requirements/quality/README.md#req-q-008---verify-release-promotion).
The linked requirement entries own the normative quality properties and thresholds.
