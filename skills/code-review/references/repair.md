# Targeted repair and refresh

Use `reviewmatic repair-review --artifact-root ROOT --kind presentation|fix|decision`
for a finalized new guided plan. This returns one editable draft copied from the
actual finalized source, not an empty review template. Older plans are historical
only and require ordinary preparation; never migrate them or execute their old
guarded actions. A repair updates `runbook.md` atomically and never publishes.

Record `repair.rationale` and `repair.checks`. Compare the original and new meaning
yourself; structural checks do not prove semantic equivalence. Do not request
confirmation for each ordinary local edit. The user controls publication.

- `presentation`: wording with unchanged claims and requirements, layout, commands,
  positions, or fix representation. Changed fix representation must produce the
  same complete tree, including file modes, on the exact reviewed revision.
- `fix`: a different correction of an already confirmed problem. Inspect affected
  consumers and failure paths and run relevant tests. No new critic is mandatory.
- `decision`: changed findings, risk assessments, requirements, or verdict. Obtain
  a new independent targeted critic in `critics`, update `critic_count`, and give
  every candidate an explicit disposition. Do not repeat unrelated review scope.

If meaning is uncertain, use decision repair. If needed checks or evidence are
unavailable, stop and report the exact limitation; preserve the current plan and
unfinished draft. Never automatically expand to a broad review or invent checks.
Run `check-review`, repair the same draft, then `finish-review`.

For changed MR facts use `refresh-review --draft DRAFT`, not a new empty review.
The runner retains findings and dispositions and updates current thread bindings.
Reassess the reported delta and affected consumers. Old critic receipts remain in
the old draft and are never rebound by replacing digests. Obtain real independent
coverage when the changed analysis scope requires it.

When `finish-review` returns `refresh_required` for CI-only drift, it preserves
analysis and the original critic receipts and attaches an immutable `ci_snapshot`.
Update CI classifications and all affected CI prose/checks in that same draft,
then finish again. Changed code, discussions, identities, or release basis are not
CI-only drift. A failed schema is an input error, not evidence for a SemVer fallback.
