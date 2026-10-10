# Guided remote review

The agent owns analysis; `reviewmatic` owns collection, bindings, validation, freshness, verdict derivation, and finalization. Use the guided commands below; never reconstruct transitions or inspect the runtime source.

## One editable draft

1. Run `reviewmatic start-review --url MR_URL --review-mode MODE --locale LOCALE --incremental INCREMENTAL`
   (modes `fast|normal`, locales `en|ru`, incremental `auto|off`) with
   `--repo-root CHECKOUT`: the runner verifies the exact base/head objects in
   that checkout and stops with an instructive error otherwise — it never
   clones a repository for the MR. The runner prepares a managed review
   worktree at the exact MR head, returns it in `review_worktree` with the
   source repository and exact base/start/head/target refs, and critics read
   all code there without recollection. Inspect the evidence, context, and
   `inspection_path`; the index holds the complete diff and exact base/head
   source snapshots, not working-tree files, with missing, binary,
   non-regular, or over-budget snapshots explicit. Never duplicate MR
   collection with `glab mr view`. Read `draft_schema_path`, `input_contract`,
   and `input_examples` immediately. Complete the returned context package
   template and record it before launching critics; assigned questions are
   answered by critics in `question_answers` and every `not_verified` answer
   is checked by the primary in `question_verifications` — see
   `references/context-package.md`.
2. Record the panel with the returned `record-participants` action before
   any receipt exists: critics plus the arbitrator. Review code and
   discussions only as far as orchestration requires. Fill the returned
   `draft_path` identity fields (`run_id`, `session_id`, `low_risk`) through
   `record-input`; every finding, disposition, CI assessment, and content
   section arrives through the arbitration receipt. Each disposition includes
   `id`, `decision=accept|reject`, `reason`, and `dependencies` with `paths`,
   `thread_ids`, `metadata_fields`, and `ci`; accepted candidates may use
   empty lists, rejected ones concrete scope dependencies. Preserve receipt
   identities and distinct finding ID prefixes per critic; `severity_override`
   records `original_severity`/`severity`/reason, `duplicate_of` names the
   canonical finding, and `existing_thread` fix records bind `thread_id`
   without dropping the defect from readiness. Complete every generated
   `ci_job_assessments` entry from its bounded trace: `trace_evidence` is an
   exact non-empty substring of the job's collected redacted trace, with
   project/pipeline/job IDs preserved.
3. The arbitration receipt completes `content`: semantic
   chat/architecture/metadata/SemVer assessments, every catalog label, checks,
   concrete `finding_publications`, previous-finding assessments, recommended
   issues, and thread decisions. Metadata input is the flat five-field
   assessment, not an `observed` wrapper; publication input has exactly
   `finding_id`, `type`, `path`, `line`, `old_line`, `body`, `fix_mode`, and
   `patch`, optionally `suggestions`/`split_rationale`/`patch_reason`
   (mandatory for fallback). The runner derives findings, candidates,
   revisions, paths, digests, and verdicts — never add derived fields or copy
   data between artifacts. Grouped thread suggestions may carry prose-only
   `routing_response` for a new-position reply; it never replaces the shared
   explanation or parts.
4. Run the returned `reviewmatic check-review --draft DRAFT_PATH`: it validates
   locally without GitLab reads, publication artifacts, or progress changes;
   fix the reported fields in the draft and repeat.
5. Run the returned `reviewmatic finish-review --draft DRAFT_PATH`: it
   revalidates locally — no GitLab request runs at finalization — and
   atomically publishes the plan, Markdown, and baseline. Post-review drift
   is caught by an explicit `refresh-review` and the head check guarding
   every manual publication block. Print `chat` verbatim and one fenced
   `plan_command`; never run any publication command during the review.

Use `reviewmatic resume-review --artifact-root ROOT` after interruption: the
same editable draft, participants, and pending panel steps return without
recollection, and a recorded composition is never asked for again. Use
`reviewmatic refresh-review --draft DRAFT` for changed evidence while
retaining the selection; the old plan and draft are preserved. Finalized new
plans use `repair-review` (`references/repair.md`). Collection, validation,
and finalization timings are separate from model and subagent time; never
blame review analysis on the runtime or hide validation-repair loops.

## Review panel: critics and arbitrator

The guided path records the same panel the run path and
`references/review-panel.md` define: one recorded selection
(`reviewmatic record-participants --draft DRAFT --input participants.json`:
critics plus arbitrator), then parallel independent critics, then one separate
arbitrator. Ground the pool in the host's agent inventory before composing
options (`review-panel.md`); set the critic count through the selection
itself; the selection is fixed once receipts exist. Import each independent
critic receipt with `reviewmatic record-critic --draft <draft-path> --input <receipt>` and its exact `--participant` name; the runtime binds the receipt
identity to the participant and rejects a re-used one. Each critic performs one complete independent review: findings plus answers
to its assigned questions, from the same package and snapshots, without
other critics' output, GitLab recollection, or file-map rebuild. Every
finding traces its symptom to the changed lines through concrete code
(symptom-path tracing), and unreachable-code claims prove unreachability
from a real entrypoint.

Absence of `critic` is not a blocker. Supply the recorded context package
path, the exact snapshot paths, the materialized
`references/simplification-criteria.md` path, accepted scope and user
decisions, but no other reviewer's conclusions. The critic reads the package
as its primary context, answers every question assigned to critics in
`question_answers` with one verdict — `confirmed`, `refuted`, or
`not_verified` — plus evidence or a concrete reason bound to that question's
`context_digest`, and with several critics the runtime enforces the pair rule
(one critic's answer never covers another's assignment); edited-question
re-records retire affected answers into `superseded_question_results` and a
late superseded-bound receipt is refused (`references/context-package.md`
owns the arithmetic). Request complete detailed findings in the required
report envelope — `review_report` is valid for routed specialists — and
populate the returned receipt template: its `run_id` is pre-stamped with this
run's identity (keep it), and `session_id` is the critic subagent's real
native session id, never a copied or invented label. Never ask a child to
guess its identity, switch providers, invent an identity, fabricate a
receipt, or run `opencode run` to evade a failed delegation policy; if the
host cannot launch any independent native subagent of the current agent, report that capability failure
before an extended review instead of weakening depth, and never replace or
omit a failed specialist without reconciling the selected critic count.

When the last critic receipt is imported, the arbitrator task arrives with
the same package binding, every receipt verbatim, and the reported
contradictions; its duties, ladder, import, and refusal contract live in
`references/review-panel.md` and apply unchanged.

## Compatibility and verdict

Existing v2 artifacts and low-level commands (`prepare`, `context`,
`template-review`, `record-artifact`, `finalize`, `finalize-review`,
`scaffold-review`, `status`, and `report-review`) are supported for old
callers; never mixing them with a guided draft; progress stages stay inspectable.

Every accepted non-low finding blocks `ready`; failed or canceled CI jobs
require trace-supported classification across child/downstream pipelines,
with only proven manual process gates non-blocking and missing, active,
stale, incomplete, unknown, or unclassified CI evidence staying blocking.
Every previous finding and critic candidate needs an explicit arbitrator
verdict; generated verdicts never replace the arbitrator's semantic
assessment or authorize publication.
