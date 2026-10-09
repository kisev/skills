# The inverted tail: render, edit prose, finalize

For the primary `run` path the order is decision → shared render → record-prose → finalize.
For a separate draft, after its decision is recorded, run
`reviewmatic render-review --draft <draft-path>`: the runtime renders the
content draft from accepted primary and critic findings and their publication
intents. A line fix uses a semantic `target: {path, before}` with the exact
source excerpt and a `replacement` string. The runtime derives its anchor and
`suggestion:-N+M` range, including ordinary multi-line fixes. For separate
positions use semantic `parts` with a source target, replacement, and optional
explanation per part, plus a judged `split_rationale`. Multiple matches ask for
a distinguishing source excerpt, preserving the existing prose. Never solve
ambiguity by guessing a line or re-authoring the complete structure.
An existing-thread intent binds one prepared thread named by its dependencies.
The runtime materializes `content-prose-<digest>.json` next to the draft,
carrying only the prose and semantic fields with structurally detectable
placeholders. Edit that one file (fill the placeholders, keep the row ids) and
apply it with `reviewmatic record-prose --draft <draft-path> --input <prose>`.
Structural keys in the prose file are rejected loudly; after rendering,
`record-input` over rendered fields requires a recorded repair kind, and a
draft with unfilled placeholders is not finalizable - `check-review` answers
with fill guidance instead of raw rule errors. Check the result before
finalizing. Patch companions and revisions are stamped during plan creation,
not supplied in the prose file. This routing is the precedence: render, prose, finalize; the
structural path is repair (`references/repair.md`).
Before finalization `run` checks for drift. Explicit
`reviewmatic re-anchor-review --artifact-root <root>` uses that same mechanism;
`reviewmatic re-anchor-review --draft <draft-path>` checkpoints a validated
rendered draft and hands off to the shared run tail. Unchanged evidence leaves
authorship untouched. Changed evidence creates an authorship checkpoint with
the original decision, prose, panel, and bound receipts, then asks for a fresh
delta check from the selected verifier in a new independent native session.
The stop provides exact new evidence/context/worktree paths, the delta, affected
conclusions and dependencies, and a ready template. Read related consumers too.
Line mapping proves a publication position, never the truth of a finding.
Record the completed check with
`reviewmatic record-delta --artifact-root <root> --input <delta-check>`.
Every affected conclusion gets concrete evidence and one verdict: `confirmed`,
`refuted`, `changed`, or `not_verified`. Refuted conclusions need the addressed
`accept_refutation` resolution; changed findings need `revise` with their
revised finding and stable ID. New delta findings need their semantic
`new_dispositions`, not a repeat of the entire review. `not_verified` never
passes by setting a resolution. Confirmed conclusions and prose carry forward;
changed or ambiguous fixes return the same prose surface for addressed edits.
Original digests are never overwritten. Historical checks certify the old
snapshot; a separate current receipt and delta-result record certify what was
checked or carried on the new snapshot.
New runbooks do not inherit historical IDs, revisions, or ledger obligations.
Follow-ups remain proposals without an `update_issue` action. Within an unfinished
run, confirmed authorship is retained across drift. CI-only changes update CI
assessment without requiring code analysis. New discussions are checked
substantively, and head changes require delta and affected-conclusion checks. Original
critic evidence and CI/SemVer texts remain in private history; their user-facing
Markdown/chat projections scrub known current and historical SHA tokens while
preserving revision links and executable fix code. The live ≤15-minute budget
requires measurement and never waives a necessary wider delta verification.
