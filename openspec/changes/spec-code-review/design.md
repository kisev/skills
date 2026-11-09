# Design

> Draft capture from the owner's exploration on 2026-11-09. Not final: the
> confirmed decisions below are settled; the open questions at the end block
> the capability spec and the task breakdown.

## Context

The current skill is one of the heaviest in the repository: `SKILL.source.md`
is 8.1 KB, the 17 authored references are 118 KB, and the built archive is
28 files / 340 KB including a 108 KB JSON schema. The runtime is roughly
23k lines of Python with 37 public subcommands. The primary path is a
one-process `reviewmatic run` with eight authoring stages; a marked
step-by-step repair path and legacy v2 commands remain supported. The
contract test in `apps/reviewmatic/tests/test_skill_contract.py` pins the
runtime command surface, the skill texts, and the documentation map to each
other.

Parts of the current contract that the new boundary touches directly:

- `references/context-package.md` seeds `solves-original-problem` for
  critics. It is the fulfillment question, so it stays and moves first.
- `references/review-panel.md` makes the arbitrator weigh those answers. That
  is fulfillment, not task assessment, so it stays in principle.
- `references/necessity-doctrine.md` and
  `references/architecture-checklist.md` mix task necessity with
  implementation review. The necessity half is outside the skill; the
  fulfillment half stays.
- `references/run-path.md` treats `--incremental off` as an explicit opt-out
  only. Clean and incremental runs are both first-class in the new model.
- `apps/reviewmatic/README.md` says `--repo-root` is optional with a managed
  clone fallback, while `review_worktree.py:474` requires a checkout. The
  README is stale.
- OpenSpec is not mentioned anywhere in `skills/code-review/` or
  `apps/reviewmatic/src/`. Related GitLab issues are collected as
  `iid`/`title`/`state`/`web_url` only (`context.py:852`), which is thinner
  than the task context the review needs.

## Goals / Non-Goals

**Goals:**

- One central question: does the change solve the task it was made for?
- The task definition is an input; the skill does not re-assess the task.
- The human confirms the review baseline before assessment.
- Doubts in the baseline are explicit, separate from code findings, and
  never silently resolved.
- Clean and incremental runs are first-class and explicitly selected.
- A human-focused runbook; no autonomous remote actions.

**Non-Goals:**

- Triage, planning, decomposition, and specification authoring.
- Deciding the necessity, priority, or product scope of the task.
- Posting or publishing anything automatically.
- Reconstructing a full OpenSpec change when the project has none.
- Release policy, SemVer, and labels as default review content. They may
  return as an optional block, not as the center.

## Decisions

### D1. Fulfillment is the center; the task definition is input (confirmed)

`code-review` answers whether the implementation fulfills the agreed task.
The definition of that task comes from upstream and is taken as given. The
skill may flag that the definition is ambiguous, contradictory, or
insufficient to judge fulfillment; it may propose a targeted edit to an
existing change document; it does not re-run triage or planning, and it does
not author a new specification.

The seeded `solves-original-problem` question is the fulfillment question,
not a task-level question. It stays and becomes the first question of the
review.

### D2. Three levels (confirmed)

```text
[outside the skill]
  task assessment -> agreed baseline (goal, criteria, constraints, decisions)
                              |
                              v
[inside the skill]
  1. load the baseline
  2. confirm the review criteria with the human
  3. answer the fulfillment question with evidence
  4. mark implementation divergences and risks
  5. record baseline doubts, with targeted document edits when warranted
  6. produce the runbook
```

### D3. Baseline loading and doubts (confirmed)

- **OpenSpec present:** locate `openspec/changes/<id>` in the reviewed
  checkout, preferring changed paths; ask once when the choice is
  ambiguous. Read `proposal.md`, `design.md`, and `tasks.md`. External
  OpenSpec stores are outside the initial scope.
- **No OpenSpec:** collect the available task context — linked issues, MR
  description, and human answers. Record goal and acceptance criteria as
  known, unknown, or assumed. If the baseline cannot support the
  fulfillment answer, record `not_verified`, name the missing input, and
  recommend the task/spec skill or a human decision. Do not author a spec.
- **Baseline doubt:** one row naming what is ambiguous, the possible
  readings, which reading the implementation followed, and who decides. A
  doubt is never silently resolved and never becomes a code finding.

### D4. Keep, demote, cut (direction, not final)

| Current capability | Direction | Reason |
| - | - | - |
| `glab` GET collection, exact snapshot, freshness | keep | routine the human should not repeat |
| Baseline loading (OpenSpec change, issues, MR context) | keep, extend | the fulfillment question needs it |
| Context package: goal, criteria, constraints, questions | keep | the baseline for the review |
| `solves-original-problem` | keep, promote | the central question |
| Implementation-vs-intent assessment | keep, main work | the review itself |
| Human runbook | keep, reshape | output for a human decision |
| Manual publication | keep | no autonomous remote actions |
| Local WIP mode | demote | the primary scenario is an MR |
| Independent second opinion | demote, optional | the human checkpoint matters more |
| Profiles, session modes, `fast`/`normal` | demote | the mode matrix is part of the weight |
| SemVer, release policy, labels | demote to optional | not fulfillment |
| Architecture/simplification criteria | demote | line-level detail the human wants to delegate |
| Panel poll and mandatory multi-critic arbitration | cut from default | machine concern, not a human decision |
| OCR critic | cut | external CLI with narrow value |
| Suggestions, patches, thread replies as default | cut from default | the owner asked for problem marks, not fixes |
| Decision/render/prose pipeline | cut | one authored runbook replaces it |
| Repair paths and legacy v2 commands | cut from the primary surface | one flow instead of three |
| 37 public subcommands | reduce to roughly six | collect, prepare, confirm, assess, runbook, refresh |

### D5. Clean and incremental are explicit (confirmed direction)

- `--fresh` ignores prior review context.
- `--incremental` reuses the prior runbook, answers, and confirmed
  baseline; it always re-reads the change documents and re-confirms the
  baseline when they changed.
- No auto mode decides this silently.

### D6. Output is a human runbook, not a publication plan (confirmed direction)

The runbook is organized around what the human must decide and ask, not
around a list of machine actions:

1. task baseline and the criteria the review was judged against;
2. fulfillment verdict: fully, partially, or not solved;
3. baseline doubts, with possible readings and the deciding party;
4. implementation divergences and risks, with `file:line`, no suggestions;
5. questions for the author or the human;
6. an optional metadata/release block when the project needs one.

Exact refs stay private. Publication remains manual.

## Risks / Trade-offs

- [Cutting suggestions and patches reduces author utility] -> keep them as a
  separate opt-in skill or a later block; do not bake them into the default.
- [A narrow review misses task-level defects] -> baseline doubts are
  first-class and always surfaced; the human decides.
- [A thin runtime loses binding and freshness] -> keep exact snapshots,
  digests, and freshness checks in the runtime; move only authoring out.
- [The OpenSpec change may live outside the reviewed repository] -> ask once;
  external stores are out of scope initially.
- [The protocol becomes a megacombine again] -> one checkpoint and one
  output; every retained feature must serve the fulfillment question.

## Open Questions

These change the approach and the task breakdown, so they block `tasks.md`
and the capability spec. Recommendations are defaults, not decisions.

1. **Runtime role.** A) thin evidence/binder runtime; B) trimmed workflow
   engine; C) no runtime, `glab` and `git` only. Recommendation: A.
2. **Independent review depth.** A) one reviewer plus an optional second
   opinion; B) panel of two plus an arbitrator by default; C) none.
   Recommendation: A.
3. **Local WIP mode.** A) keep a thin local lane later; B) a separate skill;
   C) drop it. Recommendation: A.
4. **Final cut list.** Confirm the cuts in D4, in particular the panel, OCR,
   suggestions/patches, SemVer/labels, profiles, session modes, and the
   repair/legacy surfaces.
5. **Incremental reuse.** A) prior runbook, answers, and baseline only; code
   is always reassessed against the current snapshot; B) also reuse prior
   code analysis when the snapshot is compatible. Recommendation: A.
