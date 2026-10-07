# Incremental GitLab review

This contract covers one exact GitLab MR. Local WIP follows `local-review.md`.

## Selection and fallback

The primary `reviewmatic run` uses `--incremental auto`. Use `--incremental off`
only when the user asks to start from scratch or ignore the previous review.
"Full review" alone can describe depth and does not disable delta analysis.

An eligible finalized snapshot supplies the comparison boundary for incremental
analysis, including OCR. Target identity, authenticated user, role, complete evidence, compatible
contracts, unchanged base/start refs, and verified head ancestry must match.
Changed refs, incompatible or unavailable history, removed discussions/notes,
or unavailable local objects select full analysis with `fallback_reasons`.
Incomplete **current** evidence still blocks completion.

History and delta eligibility are separate. `incremental.history_context` gives
critics and the arbitrator previous findings, proposed issues, rejected candidates,
decision reasons, and their snapshot bindings as advisory context. Missing or
incompatible history produces warnings, not a mandatory repair of old artifacts.
Never delete or rewrite historical artifacts to make a new review pass.

## Current analysis and independent runbook

Use a delta-triggered scope. Start from `incremental.incremental_delta`: changed code paths, discussions,
standalone notes, metadata, label catalog, and CI are distinct inputs. Inspect
unchanged callers, consumers, configuration, and contracts where needed to prove
the delta's effects. Do not repeat the complete historical diff without a reason.
Read complete current conversations, including resolved threads and replies.
Thread closure, approval, green CI, and "Fixed" do not prove correctness.

Each run builds a standalone current-snapshot runbook. This replaces mandatory
historical synchronization: no transfer of all findings or issues, stable old IDs,
historical revisions, `update_issue`, previous-finding assessments, or cumulative
ledger coverage is required. A previous proposal absent from current analysis
does not enter the new plan. Report a currently observed defect even if the same
problem was reported before, including when its current ID differs.

A changed incremental review uses the selected independent panel. Each required
independent critic supplies a fresh receipt. The panel uses fresh
receipts bound to the delta digest. Model critics and the arbitrator receive
current snapshot paths and advisory history. OCR reviews `from_head..head` and
receives the same history with the previous findings touching changed paths in
its background. Historical IDs in its receipt describe consultation coverage,
not mandatory entries in the current runbook. Only a background above the OCR
CLI limit excludes that engine. If a required critic is unavailable, block the
current review without replacing the previous result.

When nothing changed, preserve mode `unchanged`, omit the panel, and produce a
fresh decision and runbook from the current conversation audit. Never replay an
old plan or its publication commands as a new result.

## Authorship and freshness within a run

The normal tail is recorded decision, missing prose/semantic choices, then
finalization through `run`. Return a prepared `finding_id` unchanged. Do not create
or reconstruct machine identities, positions, ranges, bindings, or stamps.
Unknown, duplicate, or substituted identifiers are refused. A semantic source
target `{path,before}` plus `replacement` supports ordinary multiline fixes.
Use structural repair only for a structural change, not for multiline text.

The runtime derives the SemVer basis and bindings from complete catalogs and
local Git proof. Address only missing policy and impact judgments. A fallback
names the unavailable proof. Label input rows contain exactly
`{name,status,rationale}` and retain the complete catalog. Recorded rejected
candidates reuse their decision reason and source binding, with no repeated
authorship or invented rationale for a validator.

Resume retains filled prose. Drift checkpoints original decisions and receipts
without replacing their digests. Pipeline completion with unchanged code asks
for current CI assessment, not a fresh code analysis. Changed discussions require
substantive conversation checks. Head drift requires delta and affected-conclusion
verification, preserving ready authorship. Position mapping is not proof of truth.
Unverified current evidence or ambiguous targets remain blocking and return a
specific field and correction action, not an instruction to rewrite the panel.

## Publication and compatibility

Follow-ups remain proposals. Determine whether a current action is already
published by reading current GitLab discussions, notes, and issues, never from
local command markers or an old runbook. Publication stays manual under
`publication.md`, with no automatic replay or publication receipt.

Original evidence remains private JSON. User-facing copied text hides known
current and historical SHA tokens while preserving immutable revision links,
executable positions, and fix code. Contracts 1 through 6 remain readable as
history and select full analysis instead of being migrated or executed.
Release/tag or target changes can invalidate the delta basis and require full
analysis. A next-release estimate needs current proof, not just an unchanged MR.

Measure live tail duration, refusals, and repeated cycles separately. Green
offline tests do not prove the live target of at most 15 minutes and never justify
less analysis.
