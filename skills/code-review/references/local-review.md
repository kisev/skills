# Local review and fix verification

## Prepare

Use the existing checkout or Git worktree; run:

```sh
reviewmatic prepare-local --repo-root <checkout> --incremental auto
```

Without `--ref` the scope is exactly the uncommitted work against HEAD: staged,
unstaged, and non-ignored untracked changes. Already made commits do
not enter the scope automatically. If the user explicitly names the
local branch or revision this work merges into, pass `--ref <comparison-ref>`:
the scope then also includes the commits from the merge base of that revision with HEAD. Never derive
`--ref` from an upstream, tracking, or guessed target branch, and never
fetch. Retain a supplied `--ref` across invocations: the returned `review.previous_ref` names the retained boundary; the runner returns `review.mode`, the reason, the
previous report, and a section delta; `scope-review --artifact-root <root>`
re-prints the overview.

An `empty_scope` result means the selected boundary contains no changes:
Stop there and ask the user how to proceed. Offer supported options:
compare against an explicitly named local branch or revision with `--ref`, or
review a specific GitLab MR. Do not select an upstream or target branch automatically and do not finalize an empty run as a review. A `--ref`
missing, ambiguous, or without a common merge base with HEAD — e.g. `dup~0`
when `dup` matches both a branch and a tag; pass a fully qualified ref like
`refs/heads/dup` — preparation stops with that concrete reason; never fetch,
substitute another base, or quietly fall back to reviewing only the
uncommitted work.

Comparison mode:

- `full`: first review, incompatible or unavailable previous evidence, or an
  explicitly requested fresh audit; state the reason first.
- `incremental`: verify previous findings and inspect changed sections with
  callers, consumers, contracts, and failure paths.
- `unchanged`: check previous dispositions and any new user decisions; do not launch a new broad technical audit or require a fresh critic solely because the skill was invoked again.

Use `--incremental off` only for an explicit new full audit; "review again"
or "full review" alone never discard prior decisions. A staging change may
alter sections without behavior change: assess it, do not invent a defect;
incomplete evidence blocks completion.

## Package and panel

Record the returned local context package with its exact returned command
(`reviewmatic record-package --bundle <snapshot> --input <package>`), which
already names the immutable snapshot.
Formulate goal, acceptance criteria, constraints, prior decisions, and
questions from the conversation, applicable local documents, and the previous
report; unavailable GitLab context is normal and is never fetched; recording
or reading the package never fetches or creates a worktree.
`references/context-package.md` owns answers, bindings, and re-record
arithmetic; sequential imports merge by the critic's run/session identity and
the answer's context version, a repeated identical result is not duplicated,
and a different result under the same identity is rejected while the
original is preserved.

`full` and `incremental` may run the remote panel. Record the selection once
with `reviewmatic record-participants --bundle <snapshot> --input <participants.json>`; each participant gets one ready critic task with the
exact `reviewmatic record-critic --bundle <snapshot> --participant <name>` import
command. Local critics review the snapshot independently, in parallel, never
seeing each other's output or recollecting anything; the remote doctrine
carries these tasks. When the last receipt imports, the arbitrator resolves
every finding and contradiction, merges duplicates with stable IDs, and
returns one `code-review/local-arbitration/v1` receipt via
`reviewmatic record-arbitration --bundle <snapshot> --input <receipt>`; a missing verdict is
refused. In panel mode `record-input` carries only the `task` boundary;
finalization preserves receipts, selection, and arbitration verbatim under
`<root>/local-panel/`. `unchanged` runs panel-less; the local OCR critic
stays full-scope by design — the receipt schema has no scope fields, so an
incremental local panel runs model critics for the delta.

Compatibility needs the same checkout, comparison ref, base, HEAD, and
complete snapshots; changed HEAD, rewritten history, a changed comparison, or
lost evidence selects a full review. Carry forward still-applicable
conversation decisions even without code-delta reuse; legacy snapshots
without a finalized report are no baseline.

## Assess and retain decisions

Fill the returned template with
`reviewmatic record-input --bundle <snapshot> --input <sections-file>`; it
accepts the `task`, `task_change_reason`, `findings`, `checks`, `assessment`,
`verdict`, `question_answers`, and `question_verifications` sections, upserts
entries by identity, preserves machine bindings, and never invents a verdict.
The draft binds to the current snapshot: `prepare-local` materializes it,
`record-package` binds the package in either order, and the next snapshot
rebuilds runtime-owned fields while unfinished work survives. A malformed
section returns the exact field, reason, and expected shape. Use the latest
user-approved decision boundary (including askme answers) for `task`,
recording its basis in `decision_evidence` without inventing approval;
`task_change_reason` explains an actual change to that boundary; empty
risk/deferred lists are valid.

Retain every previous finding under its stable ID, with:

- `status`: `open`, `fixed`, `accepted_risk`, `deferred`, or `rejected`.
- `origin`: `regression`, `missed_requirement`, `pre_existing`, or
  `new_requirement`. A report defect is not automatically High; a new feature
  is not an implementation regression. Bloat outside the diff scope is
  `origin: pre_existing` and is never blocking: apply
  `references/simplification-criteria.md` and report it as optional.
- `requirement`, `scenario`, `evidence`, `consequence`: the actual contract,
  reachable conditions and assumptions, inspected code or reproduction, and
  user impact; explain why a fault-injection probe is a supported scenario.
- `minimum_fix`, `rationale`, `blocking`: necessity and cost assessed
  independently of severity; an optional improvement does not block
  acceptance, and pre-existing debt or a new requirement needs explicit scope
  approval to block.
- `decision_evidence`: the user's actual decision when accepting a risk or
  expanding scope; `reopen_reason`: changed facts or decisions justifying
  reopening a closed disposition.

Never evade continuity by assigning a new ID to the same underlying problem,
and without changed dependencies or decisions, rejected or accepted-risk
candidates stay closed. A structural validator cannot prove a model chose
the most relevant discussion: record a demonstrated semantic failure and
improve the instructions instead of adding fields automatically.

`checks` lists acceptance and regression checks plus required repository
gates, each with `passed`/`failed`/`not_run`, `required`, and evidence;
revalidate applicability — never copy old success claims. Full reviews
select `fast` (confirmed small low-risk only) or `normal` (independent critic
required); incremental reviews require a delta-scoped independent critic;
`unchanged` needs no critic unless new decisions or evidence demand a
targeted check. Record the actual run identity and scope in check evidence;
if unavailable, record `not_run` and report blocked — never simulated
self-review. `assessment` explains architecture, proportionate alternatives,
SemVer, coverage, and residual limitations.

The runner validates structure and continuity, not semantic truth; the
reviewer stays responsible for evidence and for matching checks to acceptance
criteria. Required unrun checks yield `blocked`; required failed checks or
open blocking findings yield `not_ready`; otherwise `ready`.

## Finalize and stop

```sh
reviewmatic finalize-local --bundle <snapshot> --report <draft>
```

This rechecks snapshot freshness, validates the report, and atomically
replaces the baseline with an immutable `local_review_report` bound to the
recorded package; stale evidence or an invalid report never replaces it, and
a report with open findings may still be finalized — finalized does not mean
ready. The legacy `reviewmatic finalize-local --bundle <snapshot>` checks
freshness only. Report the mode, the scope composition (which of the
committed, staged, unstaged, and untracked sections changed), and the
revisions used: the comparison ref by name and its merge base and HEAD,
exactly as present locally. Also report
required findings (closed and remaining), optional improvements, checks and
limitations, the architecture/SemVer assessment, and the absolute report
path; do not claim it is current relative to the server. Local output uses
the user's language; remote `report-review` and publication stages do
not apply.

Conclude when the agreed result is satisfied and affected regressions are
checked; never recommend another audit without a concrete uncovered risk;
when one mechanism keeps making new edge cases, explain whether simplifying
it would satisfy the goal. A genuine regression stays actionable regardless of round count or severity; a new feature or hardening proposal needs a scope
decision. Review never edits project files or starts implementation.
