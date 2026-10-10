# Deep review

The skill's conversation guidance applies to the entire thread, including
objections and applied suggestions. Apply `humanize` to each drafted thread reply
at the explicit drafting step in the discussion stage; preliminary statuses,
clarifying questions, and blocked or partial reports are written normally and
do not invoke it. Keep label proposals exclusively in
`label_assessments`; select every thread outcome explicitly after analysis —
the draft's `reply` is never an instruction to publish, and choose
`no_publication` privately when no new information is needed.

## Stage router

This router selects stages; every rule lives in exactly one stage file, and
a stage reads only its own file. The mandatory start is `run-path.md`; read
the stage file at entry, `poll-glossary.md` at the poll, and `repair.md` when
a stage refuses — never the whole set up front.

| Stage | File |
| - | - |
| Run path: the primary remote-MR review | `references/run-path.md` |
| Panel poll terms | `references/poll-glossary.md` |
| Panel composition, OCR engine, arbitration | `references/review-panel.md` |
| Context package and question bindings | `references/context-package.md` |
| Guided state machine (step-by-step path) | `references/review-state-machine.md` |
| Marked repair path's stage doctrine and discussion | `references/remote-review-stages.md` |
| Finding criteria and examples | `references/finding-examples.md` |
| Architecture and necessity priorities | `references/architecture-checklist.md` |
| Complexity candidates | `references/simplification-criteria.md` |
| SemVer and release policy | `references/semver.md` |
| Inverted tail: decision, render, prose | `references/inverted-tail.md` |
| Targeted repair and refresh | `references/repair.md` |
| Publication execution and recovery | `references/publication.md` |
| Output format: chat, runbook, prose style | `references/output-format.md` |
| Localization | `references/language-policy.md` |
| Missing-context questions | `references/question-guidelines.md` |
| GitLab workflow and label discipline | `references/gitlab-workflow.md` |
| Machine contracts of artifact schemas | `references/portable-gitlab-contracts-v2.md` |
| Local WIP review | `references/local-review.md` |
| Incremental review | `references/incremental-review.md` |
| Documentation impact of a change | `references/documentation-review.md` |
| Shared necessity and completion doctrine | `references/necessity-doctrine.md` |

For local WIP start from the previous finalized local report and snapshot (`references/local-review.md`) and stop; the remote stages
do not apply. For a GitLab MR read `references/run-path.md` first, and
`references/incremental-review.md` and `references/review-state-machine.md`
when an incremental review is selected or the run leaves the one-process path.

## Reading discipline

The orchestrator window is the scarce resource. Contracts, bindings, and
templates come from the runtime responses, the files they print, and the
recorded artifacts. They never come from reading the runtime's source code or
dumping complete JSON schemas into the conversation to derive input fields;
when a command refuses, its rule refusal is the answer, not a prompt to read
source. Never read the whole recorded context package into the main window:
critics and arbitrators receive it by path, and the orchestrator reads a
single section only when a decision requires that one. Read artifacts by path
(complete absolute filesystem paths in inline code) and pass them by path;
when a look inside a large artifact is unavoidable, use a bounded read (a
head, a targeted grep, a single section) or hand the read to the subagent
that owns the analysis. Never re-read an entire artifact into the main
window to answer a question the runtime response already answers.

## Select and pin the runtime

Before the first `reviewmatic` call, apply the runtime selection and pin
procedure exactly as `SKILL.source.md` specifies it — that entrypoint owns the
channel choice (when the channel is unclear, ask — never choose silently), the
`dev` tip resolution, the `REVIEWMATIC_FROM` pin, the PATH-binary ban, and the
`runtime-info` verification. A fresh checkout of the moving `dev` ref repeats
the same resolution and pin.

## Invocation mode

`/code-review` distinguishes a remote-MR target from local-WIP input by the
explicit request. One exact MR URL selects the remote-MR mode. An explicit
local review request selects the local-WIP mode and uses the current checkout exactly
as it is, including when that checkout is itself an existing Git worktree;
never search for an MR by branch name for it. When the request does not
clearly name one of these targets, stop and ask which one to review instead of assuming. When the
skill is invoked directly and the request leaves the task goal, constraints,
or acceptance criteria unclear, ask for the missing context once with
`question-guidelines` and wait; when it started automatically (delegated,
routed, or scheduled), do not stop for questions and build the package from
what is available, recording unknown goal and acceptance criteria explicitly.
A release MR — one that publishes or tags a version — routes to the
`release-review` skill, which owns the release verdict and its gates. Review
such an MR here only when the user explicitly requests this skill in addition.

## Run path: the primary remote-MR review

The one-process `reviewmatic run` is the primary path. `references/run-path.md`
owns that contract: the checkout requirement, the single poll with its grounding
rules, the mechanical OCR critics, the pre-stamped critic-template identity, the
post-poll drift routing, the per-stop manual commands, and the prose ending.

## The inverted tail

`references/inverted-tail.md` owns the ending order — decision, shared render,
edited prose, finalize — and the re-anchor and fresh delta check that a moved
review asks for instead of a restart.

## Necessity and completion

Apply `references/documentation-review.md` to the changed behavior's contract,
guide, mirror, and navigation impact; missing metadata does not exempt a
change. Apply the shared necessity and completion doctrine in
`references/necessity-doctrine.md` to every candidate, remedy, and follow-up.
Independent reviewers receive these decisions even when previous reviewer
conclusions are withheld to avoid anchoring. Apply `references/simplification-criteria.md`
to complexity candidates; on a remote MR, pre-existing bloat: it becomes a `recommended_issue`, and in a local review it is a finding with
`origin: pre_existing` that never blocks.

## Section map

- `references/run-path.md` — the one-process run: checkout resolution, poll,
  panel grounding, OCR execution, per-critic stops, decision, prose, and
  post-poll drift routing.
- `references/review-panel.md` — the panel composition both paths record, the
  OCR engine, the arbitrator task, and the findings discipline; the verdict
  ladder and the discussion contract live in the run path's stage files.
