# reviewmatic

[Русская версия](README.ru.md)

`@kisev/reviewmatic` is the executable runtime of the `code-review` skill: the
complete review chain (GitLab evidence collection, the review state machine,
immutable plans, manual publication) plus an interactive terminal walkthrough
of a finished review plan.

## Install

```bash
# Registry version
npm view --prefer-online @kisev/reviewmatic@latest version

# Install
npm install --global @kisev/reviewmatic

# Installed package and active CLI
npm list --global @kisev/reviewmatic --depth=0
reviewmatic --version
```

Tags can move between preview and installation; the last commands show the
installed package and the CLI resolved from PATH. For `@dev`, change both the
view and install commands.

Requires Node.js 22.13+ and the `glab` CLI authenticated for your GitLab host.
When using the dev skill distribution, install `@kisev/reviewmatic@dev` rather
than the stable npm channel. If OpenCode has the agentomatic core plugin, update
that package too and restart OpenCode: updating the CLI alone does not reload
native subagent routing hooks. Additional agent profiles are still optional.
Review state lives under `$XDG_STATE_HOME/agent-skills/gitlab/<target-key>/`, the same
layout the review commands write.

## Review chain

Agents use one editable draft, without copying bindings between decision and
content files:

```bash
reviewmatic start-review --url <mr-url> --review-mode normal --locale en
reviewmatic check-review --draft <draft-path>
reviewmatic finish-review --draft <draft-path>
```

`--repo-root <checkout>` is optional; without it the runner uses the repository of
the current directory, and a subdirectory of the checkout works too.

`start-review` collects evidence and context and returns the draft, exact-commit
inspection snapshots, and an independent critic receipt template. Its `scope`
overview summarizes the collected evidence — target identity, the MR description
flagged as author claims, changed paths, discussion threads, pipelines with
completeness markers — and names every exact snapshot, inspection, and worktree
path; `scope-review --artifact-root <root>` prints it again without any GitLab
request. It also prepares
one managed review worktree per merge request under `<repo>.worktrees/reviewmatic/`:
a detached checkout at the exact MR head, outside the user's working tree. The
result's `review_worktree` names that path, the original `source_repo_root`, and
the exact `base_sha`, `start_sha`, `head_sha`, `target_sha`, and `target_ref`.
Missing revisions are fetched over Git from the remote matching the MR's source or
target project (any remote name, forks included); the repository is never cloned,
and the user's HEAD, branch, index, files, and local branches stay untouched.
Read code from the worktree with local Git; file contents never come from GitLab.
The host agent
does the review and launches native subagents. Optional specialist critics can be
selected by count and profile; without them, ordinary independent subagents are
supported. `critic_count` records the chosen count, and `critics` contains their
actual receipts. Primary findings and critic candidates receive one disposition
each. The runner derives accepted findings, rejected candidates, verdicts, and
artifact bindings; the agent supplies the semantic assessments, concrete fixes,
label rationales, and thread outcomes.

The input package includes `draft_schema_path`, `input_contract`, and valid field
examples in `input_examples`, separately from final artifact envelopes. The
agent applies its semantic decisions mechanically with
`record-input --draft <draft> --input <sections>`: it accepts the `run_id`,
`session_id`, `low_risk`, `findings`, `dispositions`, `ci_job_assessments`,
`owner_decision_reasons`, `question_verifications`, and partial `content`
sections, upserts list entries by identity, preserves every machine field and
binding, and never invents a verdict. An existing thread decision is updated
by its `id` plus the semantic fields; the runtime keeps the prepared url,
state, and note bindings and rejects a sent value that disagrees with them. A
malformed section — `null`, a non-array, or a `null` entry — returns the exact
offending field, reason, and expected shape, and leaves the draft unchanged.
Critic receipts are imported verbatim
with `record-critic --draft <draft> --input <receipt>`; a wrapped
`review_report` envelope is unwrapped automatically, an answer bound to another
package version is rejected with the expected context version instead of being
rebound, and the runtime never creates dispositions for critic findings.
After
snapshot preparation the agent completes and records one shared context package
(`context-package` template plus `record-package --draft`): goal, claims with
sources, constraints, prior decisions, and questions, stored privately outside
the checkout and bound to the collected evidence. Recording and reading it
never contacts GitLab, and the recording response returns the ready critic
task: the recorded package path and digest, the question context versions, the
exact snapshot paths, the receipt template, and the exact `record-critic`
import command. Critics start only after the package is recorded,
receive it as their primary task context, and answer the questions assigned to
them in receipt `question_answers`; with several critics, each selected critic
answers each assigned question, and one critic's answer never covers another's
assignment. Recording stamps every question with the digest of the meaningful
content it depends on — the question itself plus the goal, acceptance
criteria, claims, constraints, agreed prior decisions, and thread registry —
and every answer and verification copies the
`context_digest` it was produced against: re-recording after an edited
question, requirement, or agreed prior decision retires exactly the affected
stale answers into the draft's
`superseded_question_results` history (fresh results for the same question
stay in place) and requires fresh results for the
affected scope, a background-only edit keeps them, and a late answer still
bound to the superseded version is rejected instead of certifying the changed
question. The primary review addresses every
`not_verified` answer in the draft's `question_verifications`, preserving the
original answer. Start the
critic as soon as these exact snapshots and the recorded package are ready, in
background alongside primary
analysis when supported. Resume verifies and reuses snapshots without rebuilding
them. No numerical response-time SLA is implied.

`dispositions[].severity_override` records original and effective severity plus a
reason without changing the critic receipt. `duplicate_of` points to the accepted
canonical finding. A finding publication of `type=existing_thread` binds
`thread_id`; its accepted thread owns the validated fix, so the defect remains in
the verdict without another publication. A user's own proposed suggestion/patch
still needs their verification reply when somebody else resolved the thread.
Later confirmation is bound by `user_confirmation.evidence_note_ids`.

The runbook starts with the derived verdict and reason, blockers, architecture and
SemVer. It shows merge impact for defects and check results for other discussions.
Suggestions stay in the original thread when its position is suitable; otherwise
a new positioned thread links back and the original receives a short routing reply.
Each patch is preceded by `patch_reason`; an available safe bounded suggestion
cannot be replaced with a patch.

`recommended_issues` are concise non-blocking proposals, not issue bodies or
creation commands: problem, proof, solution, importance, postponement risk, why
outside this MR, and an existing task if known. Full preparation belongs to
`task-prepare`; mandatory MR fixes cannot be deferred there.

`check-review` is local: it returns field paths and errors without recollecting
GitLab or freezing decisions. Edit the same draft and check again. `resume-review --artifact-root <root>` recovers that draft after interruption without remote
collection. `finish-review` validates it, rechecks complete evidence and context
once, and atomically updates the final plan, Markdown, and baseline. Stale inputs
leave the draft and previous final plan intact; use `refresh-review --draft <draft-path>`
to retain findings and reassess changed scope. CI-only drift returns
`refresh_required` with an immutable CI snapshot; update CI assessments and prose
in the same draft without another code review. Collection, validation, and finalization timings are returned
separately from host model/subagent time. Existing v2 artifacts and the low-level
`prepare`/`context`/`template-review` commands remain supported; do not mix the two
workflows in one review.
The legacy MR `pipeline` object and `latest_build_started_at`/`latest_build_finished_at`
timestamps belong to CI-only evidence. Changes to the reviewed head, metadata,
discussions or conflicts remain material and must not reuse stale analysis.

Local work-in-progress reviews use `prepare-local` and `finalize-local`;
`status`, `next`, and `assess-mode` inspect progress. Every command prints a
compact JSON result and never mutates GitLab or the checkout. Without `--ref`,
the scope is the staged, unstaged, and non-ignored untracked work against HEAD;
an explicit `--ref <revision>` adds the commits from its merge base with HEAD
and is used exactly as it exists locally, without fetching. A missing,
ambiguous, or merge-base-less `--ref` stops with a concrete reason — including
expressions such as `dup~0` when the base name matches both a branch and a
tag; pass one fully qualified ref — and a
boundary without any changes returns `empty_scope` instead of a snapshot.
Local preparation needs no `glab`, network, remote, or worktree. The local
review completes and records the same shared context package
(`record-package --bundle`) bound to the prepared snapshot with its comparison
ref and the committed, staged, unstaged, and untracked sections, and the
report binds the recorded package at finalization; the returned
`record_command` names the exact immutable snapshot path, and recording
returns the ready local critic task with the `record-input` import command.
The report is filled mechanically with
`record-input --bundle <snapshot> --input <sections>` (`task`,
`task_change_reason`, `findings`, `checks`, `assessment`, `verdict`,
`question_answers`, `question_verifications`), which preserves the machine
bindings and never invents a verdict. The draft follows the current snapshot:
`prepare-local` materializes it, `record-package` binds the recorded package
mechanically in either order, and the next snapshot rebuilds the runtime-owned
fields from the current evidence and the finalized baseline while unfinished
work on the same snapshot survives. Sequentially imported critic answers merge
by the critic's run/session identity and the answer's context version: every
original answer stays with its authorship, a repeated identical result is not
duplicated, a different result under the same identity is rejected while the
original is preserved, and a preserved `not_verified` answer keeps blocking a
ready verdict until a verification preserves it. Re-recording a
package with a changed question, requirement, or agreed prior decision
retires exactly the report's stale answers
for the previous wording into `superseded_question_results` — fresh results
for the same question stay in place — and requires
fresh answers before finalization; report answers and verifications copy the
question's `context_digest`, and finalization rejects a missing or superseded
binding, so a late result for the previous wording cannot certify the changed
question. A repeated `scope-review --artifact-root <root>` restores the
carried task, the recorded baseline, and the exact draft and template paths
from recorded state without collecting evidence again.

## Interactive plan walkthrough

The TUI is experimental and is not being developed or behaviorally tested for
blocking acceptance. Ink, PTY and server TUI suites are excluded from the default
gate. Backend collection, preparation, repair, refresh, finalization and direct
publication commands remain supported and tested, including backend helpers in
`tui/support.js`. `npm test` runs the backend suites and local worktree checks.

`runbook.md` is an equally supported interface: read the body preview and copy its
direct `glab` command. The TUI executes the same operations without a shell.

After a review the agent prints a short summary plus one command:

```bash
reviewmatic plan --artifact-root <root>
```

Run it manually in your terminal. Existing threads show the remark, the drafted
reply, the complete conversation, assessment, rationale, and GitLab link, even
when no publication is proposed. Use arrows or `j`/`k` to select and scroll,
Page Up/Down for longer lists and conversations, and left/right to move between
items. Links are clickable in terminals supporting OSC 8; `o` opens the selected
discussion in a browser. Enter opens an item and never publishes it.

Press `s` to send the reply, `r` for planned resolve/reopen after a successful reply in this manual session, or `S`
for both, then confirm with `y`. Escape cancels confirmation or returns to the list.
Read-only items offer no send/edit action. Press `e` to edit
the draft in `$EDITOR`; the plan is amended to the edited body before anything
is sent, with `runbook.md` and baseline updated together. Saving never sends.
Use `t` for reply/context views. Reading/navigation remain available during a send;
`z` cancels local waiting and `q` exits. Editing a patch body
must preserve its validated patch, reason and command. New threads, follow-up proposals,
and label updates use the same
walkthrough. Suggestions and git patches additionally offer local application:
reviewmatic creates a dedicated git worktree at the exact reviewed head, shows
the diff, and then asks for commit and push as two separate confirmations.

Reply and state change share one annotated `shell` block, guarded by `&&`. Plain
comments use the real discussion ID and resolvability returned by POST: completed
discussions can be resolved, unanswered questions and defects cannot. Direct
plain-comment blocks require `jq`. If the reply succeeded but state update failed,
inspect GitLab and do not repeat the reply blindly.

One send shows its exit code/output/error and changes state only after the reply
succeeds. There are no
publication locks, receipts, reservations, expiry, polling, automatic checks, or
automatic retries. You check GitLab in the browser and decide whether to repeat.
A timeout or cancellation does not undo an accepted request; repeating may create
a duplicate. An error or restart does not block the next manual attempt.

## Repair a new finalized plan

```bash
reviewmatic repair-review --artifact-root <root> --kind presentation
reviewmatic check-review --draft <draft-path>
reviewmatic finish-review --draft <draft-path>
```

Record `repair.rationale` and `repair.checks`. `presentation` preserves meaning and
the complete fix result, including modes. `fix` permits a different correction of
a confirmed problem after targeted consumer/tests checks, without a new critic.
`decision` changes conclusions and requires a new independent targeted receipt.
Uncertain meaning needs decision repair; insufficient checks stop without replacing
the current plan or automatically broadening review. Repair never publishes.
Suggestions are the default; related parts use `suggestions` (`path`, `line`,
`body`) and `split_rationale`. Patch fallback requires `patch_reason`, with the diff
in `patch` and prose only in `body`.

After updating the runtime, this presentation-repair sequence also regenerates
commands in existing contract-7 guided plans. Compare the old and new body previews,
positions, findings, and receipts, and record those checks before finishing. No
network collection or new full review is required. Old commands in saved plans
do not change just by upgrading. Inline commands now send `position` as nested
JSON, compatible with `glab` 1.120.0, instead of unsupported bracket fields.

Each grouped suggestion with prose is a complete comment, published without the
shared introduction. Include every necessary caveat in that part. Bare suggestion
blocks still inherit shared prose. The runbook renders exact duplicate checks once.
Thread readiness and patch-fallback checks apply equally to guided drafts and
low-level scaffolding, even when an older decision omits `blocking_thread_ids`.
A routing-only reply is editable prose, not a suggestion publication. Its optional
`routing_response` preserves the edit through presentation repair without changing
the shared explanation or positioned suggestion code. Editing suggestion code
still requires targeted fix repair.

## Worktree registry

Created worktrees are recorded in
`$XDG_STATE_HOME/agent-skills/reviewmatic/worktrees.json`; review worktrees
prepared by `start-review` are recorded in `review-worktrees.json` beside it.
The shared registry file is updated under one short lock, so parallel
preparations of different merge requests keep both records, and no fetch runs
under that lock. Review worktree paths end with a short hash of the full host,
project, and MR identity, so colliding readable names and truncated long
project paths never share a tree. A managed tree under the retired layout
without the hash is never reused, moved, or deleted automatically:
preparation stops with a concrete manual migration instruction — preserve the
active review and local changes, remove the tree with
`git worktree remove`, and the next run replaces the stale record and creates
the hashed path. Nothing else is deleted
automatically; `reviewmatic worktree list` prints the fix-application registry
with commit and push state per worktree.

## Compatibility contract

Existing v2 plans and single-critic receipts remain readable history. Only new
contract-7 guided plans support repair; old guarded actions are not executable and
are not migrated automatically. Live legacy state is not deleted. Multi-critic
receipts add optional `contributors` and require the updated runtime; the shared
schema and TS copy are checked together. Canonical JSON and digests are validated
against the Python reference in tests.
The package creates no state on `--help` or `--version`.
