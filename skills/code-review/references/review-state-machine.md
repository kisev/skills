# Review state machine

The runner owns the remote-review lifecycle. Treat every command result as a
state transition, follow its `next_action` exactly, and use `status` or its
`next` alias to recover after an interruption. Do not guess arguments after a
failed command.

## Stages

| Stage              | Meaning                                                                   | Safe transition                                                          |
| ------------------ | ------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `prepared`         | Current content-addressed evidence exists.                                | Collect context.                                                         |
| `context_ready`    | Role, threads, exact Git context, mode, and locale are bound.             | Follow the returned transition.                                          |
| `critic_missing`   | The selected mode requires an independent recorded critic.                | Generate, complete, and record the critic template.                      |
| `finalize_missing` | Context and required critic evidence are present.                         | Revalidate current evidence with `finalize`.                             |
| `decision_missing` | A fresh finalize report exists.                                           | Generate and complete the decision template, then run `finalize-review`. |
| `content_missing`  | The immutable review decision exists.                                     | Generate and complete the content template, then run `scaffold-review`.  |
| `plan_ready`       | A current contract-4 plan, Markdown, baseline pointer, and digests agree. | Run `report-review`.                                                     |
| `stale`            | A stable plan or progress binding does not match current evidence.        | Follow `resume_stage` and `next_action`; never report the old plan.      |

An incomplete lifecycle is not a best-effort review. `report-review` returns
`status=blocked`, the failed stage, its reason, and a safe transition without
finding details or a review verdict.
If the current evidence artifact itself is missing or corrupt, the runner no
longer has a trusted target from which to synthesize a restart command. It
returns blocked with `next_action=null`; the user must supply the exact MR URL
again.

## Remote sequence

1. Run `scripts/review_mr.py prepare --url MR_URL --repo-root CHECKOUT
--review-mode MODE --locale LOCALE --incremental INCREMENTAL`, where the last
   three values use `fast|normal|deep`, `en|ru`, and `auto|off` respectively.
   The response creates the current progress pointer and returns a fully bound
   context action. If an old caller omits the checkout,
   `next_action.required_inputs` marks that one value for substitution before
   execution.
2. Run the returned `context` action. The runner stores the selected full,
   incremental, or unchanged mode. Do not run a parallel `glab mr view` or fetch
   the same MR data separately; the canonical evidence and context are the only
   remote-review input.
3. Inspect code from the exact local refs. Keep complete diffs and verbose tool
   output in bounded local artifacts or tool results; bring only relevant
   excerpts and summaries into the main reasoning context.
4. When `critic_missing`, run the returned `template-review --kind critic`
   action. Give the template to an independent run/session, fill its complete
   findings and identities, then run the returned `record-artifact` action. Raw
   subagent text is not a critic receipt.
5. When `finalize_missing`, run the exact returned `finalize --artifact-root`
   action. `finalize` deliberately does not accept `--evidence`.
6. When `decision_missing`, run `template-review --kind decision`, complete the
   generated private draft, and run its exact `finalize-review` action. The
   template prebinds evidence, context, finalize, critic findings, open thread
   IDs as `thread:ROOT_NOTE_ID`, and the exact-head pipeline state. Add every
   primary finding and its disposition before finalization. If a critic finding
   duplicates an accepted primary finding, reject the critic candidate with that
   reason; accepted findings must remain structurally distinct.
7. When `content_missing`, run `template-review --kind content`. The generated
   draft prebinds accepted findings, every exact catalog label, every non-system
   thread and latest-note digest, previous findings, and rejected candidates.
   Complete every empty assessment, body, fix, rationale, and check, then run
   the returned `scaffold-review` action. The runner owns standard presentation
   labels; content supplies only `locale` and semantic `chat_assessment` prose.
8. Run the returned `report-review` action and print its `chat` value verbatim.
   Do not manually reconstruct, expand, or shorten the report. A later request
   to report the existing review runs `status` and `report-review`; it does not
   repeat analysis when the plan is still current.

Private draft files are editable inputs, not finalized evidence. Empty template
fields intentionally fail validation. The runner accepts a critic only after
`record-artifact`, accepts a decision only after `finalize-review`, and accepts a
chat report only from a fresh `review-publication.md` and baseline pair.

## Verdict policy

- Every accepted `critical`, `high`, or `medium` finding is blocking, produces
  `not_ready`, and renders as `changes required`. An accepted `low` finding is
  always non-blocking.
- If no finding is blocking and the exact-head pipeline is `failed`, use
  `blocked`; it renders as `owner decision required` because job logs and the
  failure cause are not part of canonical evidence.
- Other owner decisions require a non-empty reason and use `blocked`.
- With no blocking finding, failed pipeline, or owner-decision reason, use
  `ready`.

The runner validates this policy before creating the review decision. Metadata
and thread assessments remain explicit in the plan but cannot silently turn a
low finding into a blocking one.
