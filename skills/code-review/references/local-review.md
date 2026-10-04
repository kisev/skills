# Local review and fix verification

## Prepare

Use the existing checkout — an ordinary checkout or an already existing Git
worktree — and run:

```sh
reviewmatic prepare-local --repo-root <checkout> --incremental auto
```

Without `--ref` the scope is exactly the uncommitted work against HEAD: staged
changes, unstaged changes, and non-ignored untracked files. Already made commits
do not enter the scope automatically. When the user explicitly names the local
branch or revision that this development will merge into, pass it as
`--ref <comparison-ref>`: the scope then also includes the commits from the merge
base of that revision with HEAD. Never derive `--ref` from an upstream, tracking,
or guessed target branch, and never fetch.

Retain the original `--ref <comparison-ref>` when one was supplied; the returned
`review.previous_ref` names the retained boundary. Do not infer a new comparison
boundary on each invocation. The runner stores the immutable committed, staged,
unstaged, and non-ignored untracked snapshot. It returns `review.mode`, the
reason, the previous report, a section delta, and a `report_template` with the
current evidence and previous-review digests. The response's `scope_overview`
summarizes the section composition, the carried task, and the previous review
without re-reading the snapshot; `reviewmatic scope-review --artifact-root <root>` prints it again later.

An `empty_scope` result means the selected boundary contains no changes: without
`--ref` there is no staged, unstaged, or untracked work; with `--ref` the commits
since the merge base and the uncommitted work are both empty. Stop there and ask
the user how to proceed. Offer only supported options: compare against an
explicitly named local branch or revision with `--ref`, or review a specific
GitLab MR. Do not select an upstream or target branch automatically and do not
finalize an empty run as a review.

When the named `--ref` is missing, ambiguous, or has no common merge base with
HEAD, preparation stops with that concrete reason. This includes expressions
such as `dup~0` when the base name `dup` matches both a branch and a tag: pass
one fully qualified ref (for example `refs/heads/dup` or `refs/tags/dup`) and
the expression works from it. Report the ambiguity and ask how to proceed;
never fetch, substitute another base, or quietly fall back to reviewing only
the uncommitted work.

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

Complete the returned local context package template and record it before
reviewing. Use the returned `record_command` as it is: it already names the
exact immutable snapshot, not a placeholder:

```sh
reviewmatic record-package --bundle <snapshot> --input <package>
```

Formulate goal, acceptance criteria, constraints, prior decisions, and
questions from the conversation, the applicable local documents, and the
previous report; unavailable GitLab context is normal and is never fetched.
The runtime fills the mechanical parts: the binding to the `prepare-local`
snapshot with the chosen comparison ref and the committed, staged, unstaged,
and untracked sections, plus prior decisions retained from the previous
report. Recording and reading the package never touch the network, fetch, or
create a worktree. `resume`/refresh reuses the recorded package while the
snapshot binding is current and keeps the previous package as immutable
history. Re-recording the package after changing a question, goal, acceptance
criterion, claim, or constraint retires the report's answers collected for
the previous wording into `superseded_question_results` and requires fresh
answers before finalization; editing the background keeps them. Every answer
and verification in the report copies the question's `context_digest` from
the recorded package, and finalization rejects a missing or superseded
binding, so a late result for the previous wording never certifies the
changed question. Recording returns the ready local critic task with the
package path, question context versions, and the exact `record-input` import
command. When local
critics run, they receive the recorded package as their
primary context and answer assigned questions in the report's
`question_answers`; import each critic's returned file with `reviewmatic
record-input` without rewriting it. Sequential imports merge by the critic's
own run/session identity and the answer's context version: every original
answer stays with its authorship, a repeated identical result is not
duplicated, and a different result under the same identity is rejected while
the original is preserved. Answer every `not_verified` result in
`question_verifications`, preserving the original; primary verifications stay
separate and a preserved `not_verified` answer keeps blocking a ready verdict
until then. See
`references/context-package.md`.

## Local review panel

`full` and `incremental` local reviews may run the same panel process as the
remote flow. Record the selection once with `reviewmatic record-participants --bundle <snapshot> --input <participants.json>` (`critics` plus `arbitrator`);
the recording response and the recorded package then return one ready critic
task per participant with the exact `record-critic --bundle <snapshot> --participant <name>` import command. Local critics perform complete
independent reviews of the working tree exactly as committed, staged, and
untracked in the snapshot, returning findings in the local report shape plus
answers to their assigned questions; they run in parallel, never see each
other's output, and never recollect anything. When the last receipt is
imported, the response returns the local arbitrator task; the arbitrator
confirms or refutes every critic finding, resolves contradictions, merges
duplicates while keeping prior finding IDs stable, and returns one
`code-review/local-arbitration/v1` receipt with the consolidated checks,
assessment, and derived verdict. Import it with the exact
`record-arbitration --bundle <snapshot> --input <receipt>` action; the runtime rejects
a receipt without a verdict for every candidate or contradiction and a verdict
that disagrees with the recorded findings and checks. In panel mode
`record-input` carries only the `task` boundary: findings, checks, assessment,
verdict, and answer resolutions belong to the arbitration receipt.
Finalization keeps the report artifact schema-identical and preserves the
receipts, the selection, and the arbitration verbatim under
`<root>/local-panel/`. `unchanged` mode runs without a panel.

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

Fill the returned template at `review.draft_path` mechanically with
`reviewmatic record-input --bundle <snapshot> --input <sections-file>`; it
accepts the `task`, `task_change_reason`, `findings`, `checks`, `assessment`,
`verdict`, `question_answers`, and `question_verifications` sections, upserts
findings and checks by identity, merges critic answers and verifications by
identity, preserves the machine bindings, and never
invents a verdict or a decision. The draft is bound to the current snapshot:
`prepare-local` materializes it, `record-package` binds the recorded package
into it mechanically in either order, and the next snapshot rebuilds the
runtime-owned fields from the current evidence and the finalized baseline
while unfinished work on the same snapshot survives. A malformed section
returns the exact offending field, reason, and expected shape, and leaves the
draft unchanged. Use the latest user-approved decision
boundary, including askme answers, for
`task`. Record its conversation basis in `decision_evidence`; do not invent
approval. `task_change_reason` explains an actual change to that boundary and
its user decision or corrected evidence. Empty risk/deferred lists are valid.

Retain every previous finding under its stable ID, including fixed, rejected,
deferred, and accepted-risk entries. Use these fields:

- `status`: `open`, `fixed`, `accepted_risk`, `deferred`, or `rejected`.
- `origin`: `regression`, `missed_requirement`, `pre_existing`, or
  `new_requirement`. A report defect is not automatically High, and a newly
  requested feature is not an implementation regression. Bloat or complexity
  outside the diff scope is `origin: pre_existing` and is never blocking:
  apply `references/simplification-criteria.md` to it and report it as
  optional per the necessity doctrine.
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
reviewmatic finalize-local --bundle <snapshot> --report <draft>
```

This rechecks snapshot freshness, validates the report, writes an immutable
`local_review_report`, and atomically replaces the local baseline pointer.
The report must bind the recorded context package; the runtime rejects an
unrecorded or stale package before replacing the baseline. Stale evidence or
an invalid report does not replace the baseline. The legacy
`finalize-local --bundle <snapshot>` only checks freshness and creates no review
baseline. A report with open findings may be finalized for subsequent fixes;
finalized does not mean ready.

Report the mode, the scope composition (which of the committed, staged, unstaged,
and untracked sections changed), and the actual revisions used: the comparison
ref by name and its merge base and HEAD. A named `--ref` was used exactly as it
exists locally without fetching, so do not claim it is current relative to the
server. Also report closed and remaining required findings, optional
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
