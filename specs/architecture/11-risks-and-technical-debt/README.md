# Risks and Technical Debt

Semantic specification review can detect drift but cannot prove undocumented human intent.
External host APIs may be unavailable or change within the declared compatibility
range. Live integrations remain bounded by hostless contracts and may require
manual evidence. A malformed or inaccessible local state file is reported as
incomplete rather than repaired implicitly.

GitHub Pages availability is now part of portable installation. A stale Pages
cache, partial deployment, or mismatched archive must fail digest and release
verification rather than install mixed bytes. The stable Pages URL intentionally
moves between releases; Git tags remain immutable provenance.

Portable cleanup depends on the external `skills` CLI and cannot roll back npm
cache or network effects. A concurrent unrelated `skills` process can race the
package lifecycle lock; final path and lock-state validation therefore fails
closed and restores only the bounded local snapshots. A file created inside a
target tree after final revalidation can be removed by the external CLI without a
snapshot; this accepted direct-execution boundary is documented as best-effort.
Pre-marker retired skills remain manual cleanup by design.
