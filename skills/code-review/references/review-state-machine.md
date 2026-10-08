# Guided remote review

The agent owns analysis. `reviewmatic` owns collection, bindings, draft
validation, freshness, verdict derivation, and atomic finalization. Use the
guided commands below; do not reconstruct low-level transitions or inspect the
installed runtime's source to discover input fields.

## One editable draft

1. Run `reviewmatic start-review --url MR_URL --review-mode MODE --locale LOCALE --incremental INCREMENTAL`.
   Modes are `fast|normal`, locales `en|ru`, incremental policies `auto|off`.
   `--repo-root CHECKOUT` is optional: a matching checkout is used as an
   optimization, and a missing or object-less checkout falls back to one managed
   clone per host and project under the XDG cache, so the invocation does not
   depend on the current directory. The runner prepares a
   managed review worktree at the exact MR head and returns it in `review_worktree`
   with the source repository and exact base/start/head/target refs; pass these
   exact paths to critics and read all code there without recollection.
   Inspect its evidence, context, and `inspection_path`. The inspection index
   contains the complete diff and exact base/head source snapshots, not working
   tree files. Missing, binary, non-regular, or over-budget source snapshots are
   explicit; inspect those objects separately and trace affected consumers.
   Do not duplicate MR collection with `glab mr view`.
   Read `draft_schema_path`, `input_contract` and `input_examples` immediately;
   they describe editable input separately from final artifact envelopes.
   Complete the returned context package template and record it with the
   returned `record-package` action before launching critics; critics receive
   the recorded package path as their primary task context. Assigned questions
   are answered by critics in receipt `question_answers`, and every
   `not_verified` answer is checked by the primary in `question_verifications`
   while the original answer stays untouched; see
   `references/context-package.md`.
2. Record the panel with the returned `record-participants` action before any
   receipt exists: the critic count and composition and the arbitrator, as
   described below. Then review the exact code and all discussions only as far
   as orchestrating requires — the panel performs the full review. Fill the
   returned `draft_path` identity fields (`run_id`, `session_id`, `low_risk`)
   through `record-input`; every finding, disposition, CI assessment, and
   content section arrives through the arbitration receipt. Each disposition
   includes `id`, `decision=accept|reject`, `reason`, and `dependencies` with
   `paths`, `thread_ids`, `metadata_fields`, and `ci`. Accepted candidates may
   use empty dependency lists; rejected candidates retain concrete scope
   dependencies. Preserve receipt identities and use distinct finding ID
   prefixes across critics. Optional `severity_override` records
   `original_severity`, effective `severity` and a concrete reason without
   editing the receipt. `duplicate_of` names an accepted canonical finding.
   `existing_thread` fix records bind `thread_id` without requiring duplicate
   publication or dropping the defect from readiness. Complete every generated
   `ci_job_assessments` entry from its bounded trace. `trace_evidence` must be
   an exact non-empty substring of that job's collected redacted trace, not a
   paraphrase. Preserve its project/pipeline/job IDs.
3. The arbitration receipt completes `content`: semantic
   chat/architecture/metadata/SemVer assessments, every catalog label, checks
   as strings, concrete `finding_publications`, previous-finding assessments,
   recommended issues, and every thread decision. Metadata input is the flat
   five-field assessment, not an `observed` wrapper. Publication input has
   exactly `finding_id`, `type`, `path`, `line`, `old_line`, `body`,
   `fix_mode`, and `patch`, optionally `suggestions`, `split_rationale`, and
   `patch_reason`. `patch_reason` is mandatory for patch fallback. The runner
   derives findings, rejected candidates, revisions, body/patch paths, digests,
   and verdicts. Do not add those derived fields or copy data between
   decision/content artifacts. Grouped thread suggestions may carry an optional
   prose-only `routing_response` for the short original-thread reply when the
   fix needs a new position. It does not replace the shared explanation in
   `proposed_response` or suggestion parts.
4. Run the returned `reviewmatic check-review --draft DRAFT_PATH` action. It
   validates locally without GitLab reads, publication artifacts, or progress
   changes. Fix the reported field paths in the same draft, then repeat the
   check. A presentation or patch error does not freeze the decision or require
   restarting the review. Raw commit IDs stay in private evidence, not prose
   that will be rendered into the plan; use immutable GitLab links when needed.
   The validator reports independent schema and fix errors together, including
   receipt prose and suggestion ranges. Do not bisect prose to find an error.
5. Run the returned `reviewmatic finish-review --draft DRAFT_PATH`. It
   revalidates locally — no GitLab request runs at finalization — and
   atomically publishes the local immutable plan, Markdown, and baseline.
   Post-review drift is caught by the explicit `refresh-review` and by the
   head check guarding every manual publication block. Print its `chat`
   verbatim and one fenced manual `plan_command`. Never run that interactive
   command or any publication/patch command during the review.

Use `reviewmatic resume-review --artifact-root ROOT` after interruption. It
returns the same editable draft, the recorded participants, and the pending
panel steps without recollection. A recorded composition is never asked for
again. Use `reviewmatic refresh-review --draft DRAFT` to collect changed evidence while
retaining the panel selection: the refreshed draft keeps the participants
without receipt bindings and expects fresh critic receipts plus a fresh
arbitration receipt; the old final plan and draft are preserved. Finalized new
plans use `repair-review`; see `references/repair.md`. Collection, validation,
and finalization timings are separate from model and subagent time; do not
blame review analysis time on the runtime or hide validation-repair loops
inside it.

## Review panel: critics and arbitrator

Normal and incremental reviews run as a panel: one recorded selection,
parallel independent critics, and one separate arbitrator. Unchanged mode
skips the panel but still audits every discussion. Fast mode runs without a
panel and requires explicit `low_risk=true` justified by the inspected change.

Use the host's available agent inventory, not assumed agent names. When this
skill runs directly and the panel composition was not already fixed by the
request, ask once — in the same single question round as missing task context —
how many critics, which installed `critic-*` profiles or ordinary subagents,
and which arbitrator. An explicit skip is acceptable and defaults to one
ordinary critic and one ordinary arbitrator, recorded as exactly that default.
When the skill started automatically, do not stop for questions and record the
default composition transparently. For each role an installed specialist
profile and an ordinary independent subagent running with the current session's
agent, provider, and model are both valid; specialist profiles and stronger
models are optional. Never substitute a configuration silently: the recorded
`name`, `profile`, `provider`, and `model` travel into the runbook, and the
arbitration receipt must name the selected arbitrator.

Record the selection once with `reviewmatic record-participants --draft DRAFT --input participants.json` (`critics` plus `arbitrator`); the selection is
fixed once receipts exist. Set the critic count through the selection itself;
run independent critics in parallel when the host supports it and retain every
receipt. The runner aggregates them without discarding contributor identities
and binds each receipt to its participant through the exact `record-critic --participant NAME` import command. Launch the panel as soon as the recorded
context package and snapshots are ready; join their results before validation.
Each critic performs one complete independent review: findings plus answers to
its assigned questions, from the same package and snapshots, without seeing
other critics' output, recollecting GitLab, or rebuilding the file map. Every
finding traces its symptom to the changed lines through concrete code
(symptom-path tracing), and an unreachable or dead-code claim requires
proving unreachability from a real entrypoint (reachability from
entrypoint).

If no specialist profiles are installed, launch an ordinary independent native
subagent of the current agent; no profile-selection question is needed.
Absence of `critic` is not a blocker. Supply the recorded context package
path, the exact evidence/context/inspection paths, the materialized
`references/simplification-criteria.md` path, accepted scope and user
decisions, but no other reviewer's conclusions. The critic reads the package
as its primary context and opens the snapshots directly when a detail is
unclear; it answers every question assigned to critics in receipt
`question_answers` with one verdict — `confirmed`, `refuted`, or
`not_verified` — plus evidence or a concrete reason, copying that question's
`context_digest` from the recorded package. With several critics the runtime
enforces the pair rule: each selected critic answers each assigned question,
and one critic's answer never covers another critic's assignment. Each answer
is bound to the meaningful context version it was produced against; a
re-recorded package with an edited question retires the previous answers into
the draft's `superseded_question_results` history and requires fresh answers
for the affected scope, and a late receipt bound to the superseded version is
rejected instead of certifying the changed question. Request complete detailed
findings in the host/profile's required report envelope; `review_report` is
valid for routed specialists. Populate the returned receipt template from
those findings and real native invocation run/session metadata, or use a
returned receipt when its identities are real. If the host exposes no separate
run ID, reuse the real session ID as `run_id`; do not introduce invented
labels. The OpenCode core plugin exposes current session identity to primary
and child agents without requiring optional profiles. Never ask a child to
guess its identity. Do not switch to another provider, invent a profile,
fabricate a receipt, or run `opencode run` to evade a failed delegation
policy. If the host truly cannot launch any independent subagent, report that
capability failure before an extended review rather than silently weakening
its depth. A failed specialist is not replaced or omitted without reconciling
the user's selected critic count.

When the last critic receipt is imported, the runtime returns the ready
arbitrator task: a complete arbitration input with the same package binding,
every critic receipt verbatim, and the reported contradictions. The
arbitrator is a separate selected subagent — never one of the critics and
never the orchestrating session. It confirms or refutes every critic finding
with a concrete reason grounded in targeted evidence checks, resolves every
contradiction and `not_verified` answer, merges duplicates without losing
authors or opinion differences, and records the consolidated decisions in one
`code-review/arbitration/v1` receipt imported verbatim with
`record-arbitration`. The receipt must select exactly one `merge_verdict` —
`decline`, `push_back`, `merge_then_fix`, or `merge` — with an evidence-based
rationale (the ladder and its tie-breaker are defined in
`references/workflow.md`), and a `decline` still salvages the attempted pain
into a recommended issue. Findings discipline belongs to the arbitrator: only
a finding that moves the merge verdict or readiness, or joins the action
list, reaches the runbook findings; every other candidate stays a refuted or
duplicate ledger entry with its reason, and the critics never see this
filter. It must not start a new defect search from scratch;
majority agreement or a model's name never replaces a reason. The runtime
rejects a receipt that leaves any candidate finding, merged finding, or
contradiction without a verdict, and never rewrites arbitrator text. Answers
stay attached to their receipts and are never merged away; `unresolved`
stays explicit when evidence is insufficient. No answer resolves publication
automatically.

## Compatibility and verdict

Existing v2 artifacts and low-level `prepare`, `context`, `template-review`,
`record-artifact`, `finalize`, `finalize-review`, `scaffold-review`, `status`, and
`report-review` remain supported for old callers. Do not mix them with a guided
draft. Internal progress stages remain available for inspection.

Every accepted non-low finding blocks `ready`. Failed/canceled CI jobs require
trace-supported classification across child/downstream pipelines; only proven
manual process gates can be non-blocking. Missing, active, stale, incomplete,
unknown, or unclassified CI evidence stays blocking. Previous findings and every
critic candidate require an explicit arbitrator verdict. Generated verdicts
never replace the arbitrator's semantic assessment or authorize publication.
