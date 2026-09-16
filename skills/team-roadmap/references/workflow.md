# Workflow

This skill has the fixed `roadmap` entrypoint. It reviews or updates one roadmap
artifact; it does not create work items, start implementation, prepare a retro,
or publish externally.

Resolve the profile and handle setup or remembered updates through
`references/team-profile-workflow.md`. Run
`scripts/team_workflow.py action-check` first and read the resolved profile.
Legacy explicit context updates continue to use `context-prepare` and
`context-save`; new setup uses private profiles.

## 1. Establish Scope and Ownership

Read `actions.roadmap`, the configured roadmap `document`, current `goals`, and
all `baseline.references`. Determine whether the request is a read-only review,
closed-period outcome update, future-period replanning, or a combination. Ask
only when the mutation boundary or target periods remain ambiguous after reading
the evidence.

Use the configured cadence and express evidence windows as UTC `[since, until)`.
Separate past, current, and future periods before proposing changes.

## 2. Collect Bounded Evidence

Build an evidence matrix with one row per roadmap goal and explicit columns for
planned outcome, tracker state, code or release evidence, delivered outcome,
confidence, discrepancy, and destination. Use all included profile projects and
only declared sources or user-provided evidence.

When `actions.roadmap.use_gitlab_metrics` is true, use
`scripts/gitlab_period_metrics.py` exactly as described by the retro workflow:
one project argument per included GitLab project, strict half-open boundaries,
full pagination, timestamp provenance, and explicit partial status. Query
tracker, document, or presentation sources through their declared tools and
current installed help; do not invent commands or statuses.

Evidence precedence is factual, not aspirational. A delivery signal may prove
an outcome even when a tracker state is stale, but record the discrepancy. A
merged change, a tag, and a production shipment remain distinct states. Do not
promote one to another without the configured delivery evidence.

If any required source, project, page, or goal cannot be inspected, identify the
affected rows and consequence. Continue only with a bounded `partial` result;
never hide gaps inside an aggregate status.

## 3. Reconcile Plan and Fact

Apply `actions.roadmap.history_policy` exactly. Unless the profile explicitly
states another policy, past plans are historical records: do not rewrite what
was planned after the period closed. Update factual outcomes and add clearly
labelled unplanned delivery instead.

For every goal, determine status from evidence and preserve useful details:

- Completed means the configured delivered outcome is evidenced.
- Partial or in progress states what was delivered and what remains.
- Not started has no qualifying progress evidence.
- Blocked names the external dependency and its evidence.
- Contradictory evidence remains unresolved until explained.

Every unfinished goal needs one explicit destination: a named future period,
backlog, cancellation with reason, or blocked state with owner/dependency. A
partial or not-started goal that disappears from future plans is a planning gap,
not a completed review.

Replan only future periods and only within the user's requested boundary. Use
current goals, priorities, dependencies, and capacity evidence. Do not generate
new commitments merely to fill a section.

## 4. Preserve the Document Contract

Keep the existing document structure unless the request includes a format
change. Follow profile `rules`, `status_legend`, link conventions, and period
ordering. Keep identifiers, project names, versions, and source links exact.
Avoid decorative status changes that alter meaning.

Roadmap output is planning context, not an implementation task list. Do not
create issues, epics, milestones, or external messages. Record source
discrepancies next to the affected goal unless the profile identifies another
owned location.

## 5. Write and Verify

For a review, report findings and stop without writing. For an update, write the
complete candidate document directly through `artifact-write`, then report
changed periods, unresolved conflicts, evidence gaps, and checks.

Run every applicable command in `actions.roadmap.verification_commands`. Prefer
direct linting of the target path when repository wrappers ignore untracked
files. A failed check must be fixed and rerun or reported as an explicit
limitation.

Report periods reviewed, goals completed, carried, backlogged, cancelled, or
blocked, unplanned delivery, source discrepancies, evidence completeness,
artifact path, and verification results.

Read `references/interaction-contract.md` for evidence and mutation rules
and `references/language-policy.md` for user-facing prose.
