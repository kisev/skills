# Local review and fix verification

## Prepare

Use the existing checkout and run:

```sh
python3 -I -S -B scripts/review_mr.py prepare-local --repo-root <checkout> --incremental auto
```

Retain the original `--ref <comparison-ref>` when one was supplied. Do not infer a
new comparison boundary on each invocation. The runner stores the immutable
committed, staged, unstaged, and non-ignored untracked snapshot. It returns
`review.mode`, the reason, the previous report, a section delta, and a
`report_template` with the current evidence and previous-review digests.

- `full`: first review, incompatible or unavailable previous evidence, or an
  explicitly requested fresh audit. State the reason before reviewing.
- `incremental`: verify previous findings, inspect changed sections and their
  affected callers, consumers, contracts, and failure paths.
- `unchanged`: check previous dispositions and any new user decisions or evidence;
  do not launch a new broad technical audit or require a fresh critic solely
  because the skill was invoked again.

Use `--incremental off` only for an explicit new full audit. "Review again",
"verify the fixes", "independent review",
and "full review" alone do not mean discarding prior decisions. A new reviewer
receives the agreed goal, constraints, accepted risks, and acceptance criteria.

Compatibility requires the same checkout, comparison ref, base, HEAD, and
complete snapshots. Changing HEAD, rewriting history, changing the comparison,
or losing evidence selects a full review. Previous decisions remain visible in
the returned historical report: carry forward still-applicable decisions from
the conversation even when code-delta reuse is unavailable. Legacy snapshots
without a finalized report do not constitute a baseline.

The section delta compares previous and current Git diff text; it is not an
applicable patch. Untracked deltas record added, removed, or changed paths with
hashes. Read the current files and necessary unchanged consumers. A staging
change may alter sections without changing final behavior; assess it rather
than inventing a defect. Incomplete current evidence blocks completion.

## Assess and retain decisions

Complete the returned template at `review.draft_path`, outside the checkout.
Use the latest user-approved decision boundary, including askme answers, for
`task`. Record its conversation basis in `decision_evidence`; do not invent
approval. `task_change_reason` explains an actual change to that boundary and
its user decision or corrected evidence. Empty risk/deferred lists are valid.

Retain every previous finding under its stable ID, including fixed, rejected,
deferred, and accepted-risk entries. Use these fields:

- `status`: `open`, `fixed`, `accepted_risk`, `deferred`, or `rejected`.
- `origin`: `regression`, `missed_requirement`, `pre_existing`, or
  `new_requirement`. A report defect is not automatically High, and a newly
  requested feature is not an implementation regression.
- `requirement`, `scenario`, `evidence`, `consequence`: name the actual contract,
  reachable conditions and assumptions, inspected code or reproduction, and user
  impact. Explain why a fault-injection probe represents a supported scenario.
- `minimum_fix`, `rationale`, `blocking`: assess necessity and implementation
  cost independently of severity. An optional improvement does not block task
  acceptance. Pre-existing debt or a new requirement requires explicit scope
  approval before becoming blocking.
- `decision_evidence`: the user's actual decision when accepting a risk or
  expanding scope. `reopen_reason`: changed facts or a changed user decision that
  justify reopening a closed disposition or promoting a non-blocker to blocker.

Do not evade continuity by assigning a new ID to the same underlying problem.
Previously rejected or accepted-risk candidates are not re-investigated without
changed dependencies or decisions. A structural validator cannot prove that a
model chose the most relevant discussion; record a demonstrated semantic failure
and improve the decision instructions instead of automatically adding fields.

`checks` lists actual acceptance checks, targeted regression checks, and required
repository gates, each with `passed`, `failed`, or `not_run`, `required`, and
concrete `evidence`. Revalidate applicability to this snapshot; do not copy old
success claims. Full reviews select `fast`, `normal`, or `deep`; `fast` is only
for confirmed small low-risk changes, and `normal`/`deep` require an independent
critic. Incremental reviews require a delta-scoped independent critic. Record
the actual run identity, scope, and accepted/rejected conclusions in check
evidence. If unavailable, record the required check as `not_run` and report
blocked, never simulated self-review. `unchanged` requires no critic unless new
decisions or evidence make a targeted independent check necessary.
`assessment` explains architecture,
proportionate alternatives, SemVer, coverage, and residual limitations.

The runner validates structure and continuity, not semantic truth. Reviewers
remain responsible for honest evidence, necessity, and matching the checks to
the acceptance criteria. Required unrun checks yield `blocked`; required failed
checks or open blocking findings yield `not_ready`; otherwise use `ready`.
Optional or accepted limitations may remain in a ready report.

## Finalize and stop

```sh
python3 -I -S -B scripts/review_mr.py finalize-local --bundle <snapshot> --report <draft>
```

This rechecks snapshot freshness, validates the report, writes an immutable
`local_review_report`, and atomically replaces the local baseline pointer.
Stale evidence or an invalid report does not replace the baseline. The legacy
`finalize-local --bundle <snapshot>` only checks freshness and creates no review
baseline. A report with open findings may be finalized for subsequent fixes;
finalized does not mean ready.

Report the mode and scope, closed and remaining required findings, optional
improvements separately, checks and limitations, architecture/SemVer assessment,
and the absolute report path. Local output is authored in the user's language;
remote `report-review` and publication stages do not apply.

Conclude when the agreed result is satisfied and affected regressions are
checked. Do not recommend another broad audit without a concrete uncovered risk.
If one mechanism keeps generating new edge cases, explain whether simplifying
it would satisfy the goal before requesting another layer. A genuine regression
remains actionable regardless of round count or severity. A new feature or
optional hardening proposal needs a scope decision, not another automatic fix
cycle. Review never edits project files or starts implementation.
