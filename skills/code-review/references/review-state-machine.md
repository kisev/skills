# Guided remote review

The agent owns analysis. `reviewmatic` owns collection, bindings, draft
validation, freshness, verdict derivation, and atomic finalization. Use the
guided commands below; do not reconstruct low-level transitions or inspect the
installed runtime's source to discover input fields.

## One editable draft

1. Run `reviewmatic start-review --url MR_URL --repo-root CHECKOUT --review-mode MODE --locale LOCALE --incremental INCREMENTAL`.
   Modes are `fast|normal|deep`, locales `en|ru`, incremental policies `auto|off`.
   Inspect its evidence, context, and `inspection_path`. The inspection index
   contains the complete diff and exact base/head source snapshots, not working
   tree files. Missing, binary, non-regular, or over-budget source snapshots are
   explicit; inspect those objects separately and trace affected consumers.
   Do not duplicate MR collection with `glab mr view`.
2. Select independent critics as described below. Review the exact code and all
   discussions; fill the returned `draft_path`. Put primary candidates in
   `findings`, actual independent receipts in `critics`, and one explicit
   `dispositions` entry per primary/critic candidate. Each disposition includes
   `id`, `decision=accept|reject`, `reason`, and `dependencies` with `paths`,
   `thread_ids`, `metadata_fields`, and `ci`. Accepted candidates may use empty
   dependency lists; rejected candidates retain concrete scope dependencies.
   Preserve receipt identities and use distinct finding ID prefixes across
   critics. Set primary `run_id`/`session_id` to the actual current identities.
   Complete every generated `ci_job_assessments` entry from its bounded trace.
   `trace_evidence` must be an exact non-empty substring of that job's collected
   redacted trace, not a paraphrase. Preserve its project/pipeline/job IDs.
3. Complete `content`: semantic chat/architecture/metadata/SemVer assessments,
   every catalog label, checks as strings, concrete `finding_publications`,
   previous-finding assessments, recommended issues, and every thread decision.
   Metadata input is the flat five-field assessment, not an `observed` wrapper.
   Publication input has exactly `finding_id`, `type`, `path`, `line`, `old_line`,
   `body`, `fix_mode`, and `patch`. The runner derives findings, rejected
   candidates, revisions, body/patch paths, digests, and verdicts. Do not add
   those derived fields or copy data between decision/content artifacts.
4. Run the returned `reviewmatic check-review --draft DRAFT_PATH` action. It
   validates locally without GitLab reads, publication artifacts, or progress
   changes. Fix the reported field paths in the same draft, then repeat the
   check. A presentation or patch error does not freeze the decision or require
   restarting the review. Raw commit IDs stay in private evidence, not prose
   that will be rendered into the plan; use immutable GitLab links when needed.
5. Run the returned `reviewmatic finish-review --draft DRAFT_PATH`. It validates
   again, refreshes complete evidence and context once, and atomically publishes
   the local immutable plan, Markdown, and baseline. Print its `chat` verbatim
   and one fenced manual `plan_command`. Never run that interactive command or
   any publication/patch command during the review.

Use `reviewmatic resume-review --artifact-root ROOT` after interruption. It
returns the same editable draft without recollection. If finalization reports
stale evidence, start a fresh review against the changed MR; the old final plan
and draft are preserved. Collection, validation, and finalization timings are
separate from model and subagent time; do not blame review analysis time on the
runtime or hide validation-repair loops inside it.

## Independent critics

Normal, deep, and incremental review require independent receipts. Unchanged
mode skips critics but still audits every discussion. Fast mode without a critic
requires explicit `low_risk=true` justified by the inspected change.

Use the host's available agent inventory, not assumed agent names. When critics
are required or explicitly requested for fast mode and suitable
specialist profiles are installed, ask once how many critics and which profiles
to use unless the user already chose. Prefer those selected profiles, including
additional `critic-*` profiles on different providers/models. Follow the host's
normal routing/receipt mechanism for routed specialist calls; preview and
dispatch must describe the same task. Set `critic_count` to the selected count,
run independent critics in parallel when the host supports it, and retain every
receipt. The runner aggregates them without discarding contributor identities.
Launch selected independent runs as soon as their evidence is ready, alongside
primary inspection when the host supports native background work; join their
results before validation, without supplying primary conclusions.

If no specialist profiles are installed, launch an ordinary independent native
subagent of the current agent; one critic is the default and no profile-selection
question is needed. Absence of `critic` is not a blocker. Supply the exact
evidence/context/inspection paths, accepted scope and user decisions, but no
primary findings. Request complete detailed findings in the host/profile's
required report envelope; `review_report` is valid for routed specialists.
Populate the returned `critic_receipt_template` from those findings and real
native invocation run/session metadata, or use a returned receipt when its
identities are real. If the host exposes no separate run ID, reuse the real
session ID as `run_id`; do not introduce invented labels. The OpenCode core
plugin exposes current session identity to primary and child agents without
requiring optional profiles. Never ask a child to guess its identity. Do not switch to another provider,
invent a profile, fabricate a receipt, or run `opencode run` to evade a failed
delegation policy. If the host truly cannot launch any independent subagent,
report that capability failure before an extended review rather than silently
weakening its depth. A failed specialist is not replaced or omitted without
reconciling the user's selected critic count.

## Compatibility and verdict

Existing v2 artifacts and low-level `prepare`, `context`, `template-review`,
`record-artifact`, `finalize`, `finalize-review`, `scaffold-review`, `status`, and
`report-review` remain supported for old callers. Do not mix them with a guided
draft. Internal progress stages remain available for inspection.

Every accepted non-low finding blocks `ready`. Failed/canceled CI jobs require
trace-supported classification across child/downstream pipelines; only proven
manual process gates can be non-blocking. Missing, active, stale, incomplete,
unknown, or unclassified CI evidence stays blocking. Previous findings and every
critic candidate require explicit dispositions. Generated verdicts never replace
the agent's semantic assessment or authorize publication.
