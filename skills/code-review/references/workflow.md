# Deep review

Apply `humanize` to each drafted thread reply at the explicit drafting step in
the discussion stage below. Preliminary statuses, clarifying questions, and
blocked or partial review reports are written normally and do not invoke it.
The skill's conversation guidance applies to the entire thread, including
objections, explanations and applied suggestions.
Keep label proposals exclusively in `label_assessments`. Do not repeat label
names or label recommendations in metadata `overall`, its recommendation, or
the general summary. Metadata describes only the MR's presentation and state.
Select every thread outcome explicitly after analysis. The draft's `reply` is
not an instruction to publish. When no new information is needed, choose
`no_publication` and explain that decision privately.

Read `references/run-path.md`, `references/review-panel.md`,
`references/remote-review-stages.md`, `references/inverted-tail.md`,
`references/interaction-contract.md`, `references/gitlab-workflow.md`, `references/portable-gitlab-contracts-v2.md`, `references/language-policy.md`, `references/necessity-doctrine.md`, `references/simplification-criteria.md`, `references/context-package.md`, `references/architecture-checklist.md`, `references/finding-examples.md`, `references/output-format.md`, and `references/semver.md`. Apply the necessity and completion doctrine to both targets. For local WIP follow `references/local-review.md`, then stop; the remote stages below do not apply. For a GitLab MR also read `references/incremental-review.md` and `references/review-state-machine.md`. Each rule lives in exactly one section file — this router only selects stages and pins the shared entry rules below.

## Reading discipline

The orchestrator window is the scarce resource. Contracts, bindings, and
templates come from the runtime responses, the files they print, and the
recorded artifacts. They never come from reading the runtime's source code or
dumping complete JSON schemas into the conversation to derive input fields;
when a command refuses, its rule refusal is the answer, not a prompt to read
source. Never read the whole recorded context package into the main window:
critics and arbitrators receive it by path, and the orchestrator reads a
single section from it only when a decision requires that one. Read artifacts
by path (complete absolute filesystem paths in inline code) and pass them by
path; when a look inside a large artifact is unavoidable, use a bounded read
(a head, a targeted grep, a single section) or hand the read to the subagent
that owns the analysis. Never re-read an entire artifact into the main
window to answer a question the runtime response already answers.

Select the runtime Git ref before starting: use the exact release tag that
matches a stable skill, or `dev` for a development skill. If the channel is not
clear, ask the user; do not silently choose a source. On the moving `dev`
channel resolve the tip first — `git ls-remote https://github.com/kisev/skills.git refs/heads/dev`
prints the current commit — and pin it:
`REVIEWMATIC_FROM='git+https://github.com/kisev/skills.git@<sha>#subdirectory=apps/reviewmatic'`.
Keep that exact pinned value for the whole review. Treat every `reviewmatic`
found on `PATH` as a foreign, possibly outdated binary and ignore it; the only
runtime is the pinned `uvx --from "$REVIEWMATIC_FROM"` install. Invoke every
runtime command, including each returned continuation action, as
`uvx --from "$REVIEWMATIC_FROM" reviewmatic ...`. Immediately after the first
invocation, run `reviewmatic runtime-info` once and compare the printed `commit`
to the pinned SHA: a mismatch or `unknown` means a stale uvx cache or an
unpinned install — re-pin with the exact `@<sha>` (adding
`--refresh-package reviewmatic` to the `uvx` invocation when the cache is
stale) before continuing the review. If the user requests a fresh checkout of
the moving `dev` ref, resolve a new tip and repeat the same pin.

`/code-review` distinguishes a remote-MR target from local-WIP input by the explicit request. One exact MR URL selects the remote-MR mode. An explicit local review request selects the local-WIP mode and uses the current checkout exactly as it is, including when that checkout is itself an existing Git worktree; never search for an MR by branch name for it. When the request does not clearly name one of these targets, stop and ask which one to review instead of assuming.

When this skill is invoked directly and the request leaves the task goal, constraints, or acceptance criteria unclear, ask for the missing context once with `question-guidelines` and wait; a short answer or an explicit skip is acceptable and the topic is never raised again. When the skill started automatically (delegated, routed, or scheduled), do not stop for questions and build the context package from what is available. The invocation mode follows the actual invocation, never the MR contents. Remaining unknowns are recorded explicitly in the package as unknown goal or acceptance criteria, and review continues without claiming completeness for an unknown task.

A release MR — one that publishes or tags a version — routes to the `release-review` skill, which owns the release verdict and its SemVer, compatibility, migration, rollback, and CI gates. Review such an MR here only when the user explicitly requests this skill in addition.

For GitLab, accept exactly one MR URL. Reject multiple URLs, project/list/filter URLs, and branch inference before any API call or artifact creation. Run `reviewmatic start-review --url <mr-url> --review-mode <fast|normal> --locale <en|ru> --incremental auto`. `--repo-root <checkout>` is optional: with it the runner uses that checkout as an optimization when it has a matching remote and can provide the exact objects, and a subdirectory of the checkout works too; without it, or when the checkout cannot provide the objects, the runner creates or incrementally updates one managed clone per host and project under the XDG cache, shared across that project's merge requests. The runner collects evidence and context together and returns one editable draft and exact-commit inspection snapshots. It also prepares one managed review worktree per MR under the resolved repository's `.worktrees/reviewmatic/`: a detached checkout at the exact MR head outside the user's working tree, with base/start/head objects and the fixed target revision fetched from the matching remote (any remote name, forks included). The returned `review_worktree` names that path, the original `source_repo_root`, and exact `base_sha`, `start_sha`, `head_sha`, `target_sha`, and `target_ref`; primary analysis and critics read all code from that worktree with local Git, never through per-file GitLab content requests. Preparation never touches the user's HEAD, branch, index, files, or local branches; it only fetches missing objects, writes `refs/reviewmatic/...` service refs, and manages that worktree. The worktree directory name ends with a short hash of the full host, project, and MR identity, so colliding readable names (such as `group/a-b` and `group-a/b`), different IIDs, and truncated long project paths never share a tree. A managed tree under the retired layout without that hash is never reused, moved, or shadowed by a second directory: preparation stops with a concrete manual migration instruction, and the hashed path is created only after that tree has been removed by hand. Parallel preparations of different merge requests keep both registry records. When the MR head advanced, the same worktree switches only when no review is active there, the tree is clean, and it holds no unexpected commits; otherwise preparation blocks and reports the concrete blocker — finish or refresh the active review, or resolve the reported state manually. If neither the provided checkout nor the managed clone can fetch the exact base, start, and head objects, preparation blocks with the concrete fetch failure instead of a silent fallback. Use `--incremental off` only for an explicit request such as "without incremental review", "start from scratch", or "ignore the previous review"; "full review" alone is not an opt-out. The context must bind the numeric ID and username of the current GitLab user, MR author, role, all paginated discussions and notes, project issue templates from the exact MR head, exact note permalinks, and the local base/start/head revisions. Do not duplicate canonical collection with direct `glab mr view` or parallel MR reads. Follow the critic-selection and fallback rules in `references/review-state-machine.md`: use selected installed specialists when available, otherwise ordinary independent native subagents of the current agent. Do not treat an absent specialist profile as unavailable independent review. Drive the joined stages through the marked repair path described in `references/remote-review-stages.md`.

For local WIP, use only the current existing checkout and `prepare-local --incremental auto`; do not clone, fetch, checkout, stash, reset, clean, or create a worktree. The role is `author`, there is no GitLab publication target, and unavailable remote context must remain explicit. A repeated review starts from the previous finalized local report and snapshot, not from a new zero-context audit.

## Run path: the primary remote-MR review

The one-process `reviewmatic run` is the primary path. `references/run-path.md`
owns that contract: the single poll with its grounding rules, the mechanical
OCR critics, the pre-stamped critic-template identity, the post-poll drift
routing, the per-stop manual commands, and the prose ending.

## The inverted tail

`references/inverted-tail.md` owns the ending order — decision, shared render,
edited prose, finalize — and the re-anchor and fresh delta check that a moved
review asks for instead of a restart.

## Necessity and completion

Apply `references/documentation-review.md` to the changed behavior's contract,
guide, mirror, and navigation impact. Missing metadata does not exempt a change;
report consequential omissions without launching an unrelated full document review.

Apply the shared necessity and completion doctrine in
`references/necessity-doctrine.md` to every candidate, remedy, and follow-up.
Independent reviewers receive these decisions even when previous reviewer
conclusions are withheld to avoid anchoring.

Apply `references/simplification-criteria.md` to complexity candidates: an
oversized or duplicating mechanism is an ordinary candidate with complete
finding fields, a `minimum_fix` that is itself correct and minimal, and the
doctrine's separation of pre-existing debt from the current change. On a remote
MR, bloat that predates the change is never a finding: it becomes a
`recommended_issue`. In a local review it is a finding with
`origin: pre_existing` and is never blocking.

## Section map

- `references/run-path.md` — the one-process run: poll, panel grounding, OCR
  execution, per-critic stops, decision, prose, and post-poll drift routing.
- `references/review-panel.md` — the panel composition both paths record, the
  OCR engine, the arbitrator task, the verdict ladder, and findings
  discipline.
- `references/remote-review-stages.md` — the marked repair path's stage
  doctrine (package, threads, labels, SemVer, suggestions, `record-input`,
  content, finalization); the run path applies the same judgments at its
  stops.
- `references/inverted-tail.md` — render, prose, re-anchor, and the fresh
  delta check for a moved review.
