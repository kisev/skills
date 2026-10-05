# Risks and Technical Debt

Semantic specification review can detect drift but cannot prove undocumented human intent.
The structural specification validator intentionally cannot detect prose
language, semantic duplication, requirement quality, architectural significance,
extension-boundary correctness, process meaning, or repository drift. Treating
its success as semantic proof remains a caller and reporting risk.
External host APIs may be unavailable or change within the declared compatibility
range. Live integrations remain bounded by hostless contracts and may require
manual evidence. A malformed or inaccessible local state file is reported as
incomplete rather than repaired implicitly.

GitHub Pages availability is now part of portable installation. A stale Pages
cache, partial deployment, or mismatched archive must fail digest and release
verification rather than install mixed bytes. The stable Pages URL intentionally
moves between releases; Git tags remain immutable provenance.

Portable cleanup belongs to the external `skills` CLI. Package locks, snapshots,
and rollback do not cover it, as required by
[REQ-F-005](../../requirements/functional/README.md#req-f-005---archive-owned-retired-assets).
Old guarded review actions remain historical and are not executed or migrated.
Manual publication does not promise exactly-once delivery: after timeout or
cancellation, users inspect GitLab and choose whether to repeat. Related
suggestions may be partially applied; only safely separable fixes use this form.
An agent can misclassify prose meaning or targeted-check scope; structural
validation does not eliminate this risk.
