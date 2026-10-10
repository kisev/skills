# Incremental GitLab review

One exact GitLab MR; local WIP follows `local-review.md`. The primary `run`
uses `--incremental auto` (`off` only on an explicit user request); "full
review" alone never disables delta analysis.

An eligible finalized snapshot sets the comparison boundary, including
OCR: target identity, authenticated user, role, complete evidence,
compatible contracts, unchanged base/start refs, and verified head ancestry
must match; changed refs, incompatible history, removed discussions or
notes, or unavailable local objects select full analysis with
`fallback_reasons`. Incomplete **current** evidence still blocks completion.

History and delta eligibility are separate. `incremental.history_context`
gives critics and the arbitrator previous findings, proposed issues,
rejected candidates, decision reasons, and snapshot bindings as advisory
context; missing or incompatible history produces warnings, never repairs
old artifacts, and historical artifacts are never deleted or rewritten to
make a new review pass.

## Current analysis and independent runbook

Use a delta-triggered scope from `incremental.incremental_delta` — changed code paths,
discussions, standalone notes, metadata, label catalog, and CI as distinct
inputs — inspecting unchanged callers and contracts as needed to prove the
delta's effects. Read complete current conversations, resolved threads
included; closure, approval, green CI, and "Fixed" never prove correctness.

Each standalone current-snapshot runbook replaces mandatory historical synchronization and requires no transfer of all findings or issues, stable
old IDs, historical revisions, `update_issue`, previous-finding assessments,
or cumulative ledger coverage. A previous proposal absent from current
analysis does not enter the new plan; report a currently observed defect
even if it was reported before under a different ID.

A changed incremental review uses the selected independent panel; each
required independent critic supplies a fresh receipt bound to the delta
digest. Model critics and the arbitrator receive current snapshot paths and
advisory history. OCR reviews `from_head..head` with the same history,
previous findings touching changed paths in its background. Historical IDs
in its receipt describe consultation coverage, not mandatory entries in the
current runbook. Only a compact background above the OCR CLI limit excludes
that engine: the background that both the poll measures and the critic
executes. If a required critic is unavailable, block the current review
without replacing the previous result.

With nothing changed, preserve mode `unchanged`, omit the panel, and
produce a fresh decision and runbook from the current conversation audit;
never replay an old plan or its publication commands as a new result.

## Authorship and freshness within a run

Normal tail: recorded decision, missing prose/semantic choices, then
finalization through `run`. Return a prepared `finding_id` unchanged;
unknown, duplicate, or substituted identifiers are refused; never create or
reconstruct machine identities, positions, ranges, bindings, or stamps.
Semantic `target: {path,before}` plus `replacement` covers ordinary
multiline fixes; structural repair is for structural changes only. The
runtime derives SemVer basis and bindings; label rows stay
`{name,status,rationale}` over the complete catalog, and recorded rejected
candidates reuse their decision reason and source binding, never an
invented rationale for a validator.

Resume retains filled prose; drift checkpoints original decisions and
receipts without replacing their digests. Pipeline completion with unchanged
code asks for current CI assessment, not fresh code analysis; changed
discussions require substantive conversation checks; head drift requires
delta and affected-conclusion verification while preserving authorship.
Position mapping is not proof of truth; unverified current evidence or
ambiguous targets stay blocking.

## Publication and compatibility

Follow-ups stay proposals; check what is published through current GitLab
discussions and issues, never local markers or an old runbook; keep
publication manual under `references/publication.md`. Original evidence
stays private JSON; user-facing text hides SHA tokens, keeps immutable
revision links. Contracts 1 through 6 are readable history and select full
analysis instead of being migrated or executed. Release, tag, or target
changes invalidate the delta basis; next-release estimates need current
proof. Measure live tail duration, refusals, and cycles separately — Green
offline tests never prove the live ≤15-minute tail.
