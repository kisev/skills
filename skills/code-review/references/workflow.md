# Deep review

Guidance covers the whole thread: objections and applied suggestions too.
Apply `humanize` to each drafted thread reply at the discussion stage's
explicit drafting step; preliminary statuses, clarifying questions, and
blocked or partial reports are written normally and do not invoke it. Keep
label proposals exclusively in `label_assessments`; select every thread
outcome explicitly after analysis — the draft's `reply` never instructs
publication; choose `no_publication` privately when no new information is
needed.

## Stage router

Every rule lives in exactly one stage file; a stage reads only its own file.
The mandatory start is `run-path.md`; read the stage file at entry,
`poll-glossary.md` at the poll, and `repair.md` when a stage refuses —
never the whole set up front.

| Stage | File |
| - | - |
| Run path: the primary remote-MR review | `references/run-path.md` |
| Panel poll terms | `references/poll-glossary.md` |
| Panel, OCR, arbitration | `references/review-panel.md` |
| Context package, bindings | `references/context-package.md` |
| Guided state machine | `references/review-state-machine.md` |
| Repair path doctrine, discussion | `references/remote-review-stages.md` |
| Finding criteria, examples | `references/finding-examples.md` |
| Architecture, necessity priorities | `references/architecture-checklist.md` |
| Complexity candidates | `references/simplification-criteria.md` |
| SemVer, release policy | `references/semver.md` |
| Inverted tail: decision, render, prose | `references/inverted-tail.md` |
| Targeted repair, refresh | `references/repair.md` |
| Publication execution, recovery | `references/publication.md` |
| Output format: chat, runbook, prose | `references/output-format.md` |
| Localization | `references/language-policy.md` |
| Missing-context questions | `references/question-guidelines.md` |
| GitLab workflow, label discipline | `references/gitlab-workflow.md` |
| Artifact machine contracts | `references/portable-gitlab-contracts-v2.md` |
| Local WIP review | `references/local-review.md` |
| Incremental review | `references/incremental-review.md` |
| Documentation impact | `references/documentation-review.md` |
| Shared necessity, completion doctrine | `references/necessity-doctrine.md` |

Local WIP: start from the previous finalized local report and snapshot
(`references/local-review.md`) and stop; remote stages do not apply. GitLab
MR: read `references/run-path.md` first, and `references/incremental-review.md`
and `references/review-state-machine.md` when incremental review is selected
or the run leaves the one-process path.

## Reading discipline

Contracts, bindings, and templates come from runtime responses, printed
files, and recorded artifacts. They never come from reading the runtime's
source code or dumping complete JSON schemas into the conversation to derive
input fields; a refused command's rule refusal is the answer, not a prompt
to read source. Never read the whole recorded context package into the main
window: critics and arbitrators receive it by path; the orchestrator reads
one section only when a decision needs it. Read and pass artifacts by path
(complete absolute filesystem paths in inline code); if a look inside a
large artifact is unavoidable, use a bounded read (a head, a targeted grep,
a single section) or hand it to the subagent owning the analysis. Never
re-read an entire artifact into the main window to answer a question the
runtime response already answers.

## Runtime selection and pin

Before the first `reviewmatic` call, apply runtime selection and pin exactly
as `SKILL.source.md` specifies — the entrypoint owns the channel choice (ask
if unclear — never choose silently), the `dev` tip resolution, the
`REVIEWMATIC_FROM` pin, the PATH-binary ban, and the `runtime-info`
verification. A fresh checkout of the moving `dev` ref repeats the resolution
and pin.

## Invocation mode

`/code-review` routes by explicit request: One exact MR URL selects the remote-MR mode. An explicit local request selects the local-WIP mode and
uses the current checkout exactly as it is,
including when that checkout is itself an existing Git worktree;
never search for an MR by branch name for it; if the request names no
target clearly, stop and ask which one to review instead of assuming. Invoked directly with unclear task goal,
constraints, or acceptance criteria, ask for the missing context once with
`question-guidelines` and wait; started automatically (delegated, routed, or
scheduled): build the package from what is available without stopping for
questions, recording unknown goal and acceptance criteria explicitly. A
release MR (publishing or tagging a version) routes to the `release-review`
skill, which owns the release verdict and gates; review it here only when
the user explicitly requests this skill too.

## Run path: the primary remote-MR review

`references/run-path.md` owns the primary one-process `reviewmatic run`:
checkout requirement, single poll with grounding rules, mechanical OCR
critics, pre-stamped critic-template identity, post-poll drift routing,
per-stop manual commands, prose ending.

## The inverted tail

`references/inverted-tail.md` owns the ending order — decision, shared
render, edited prose, finalize — and the re-anchor and fresh delta check
replacing a restart for a moved review.

## Necessity and completion

Apply `references/documentation-review.md` to the changed behavior's
contract, guide, mirror, and navigation impact; missing metadata does not
exempt a change. Apply the shared necessity and completion doctrine
(`references/necessity-doctrine.md`) to every candidate, remedy, follow-up.
Independent reviewers receive these decisions even if prior conclusions are
withheld to avoid anchoring. Apply `references/simplification-criteria.md`
to complexity candidates; on a remote MR, pre-existing bloat: it becomes a
`recommended_issue`, and in a local review it is a finding with
`origin: pre_existing` that never blocks.
