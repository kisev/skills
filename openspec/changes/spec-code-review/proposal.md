# Proposal

## Why

`code-review` is a core, frequently used skill (foundation decision D8). The owner diagnosed it as heavy, complex, and slow: the text corpus and the `reviewmatic` runtime grew around a full code-audit product — panel poll, multi-critic arbitration, OCR critic, SemVer and labels, suggestions and patches, repair paths — while the actual job is simpler and more human-centered.

The owner's working model: the human stays the principal participant; the LLM removes the routine so the human can focus on design, authorial intent, and principles. The task definition is produced upstream — by a person, another skill, or an OpenSpec change — and `code-review` consumes it as an agreed boundary. The skill may record a doubt in that boundary, but it does not re-run triage, planning, or specification authoring.

## What Changes

Reframe the skill around one central question: **does this change solve the task it was made for?**

- The task definition (goal, acceptance criteria, constraints, prior decisions) is an input, taken as given. Task assessment — necessity, priority, triage, planning, decomposition, spec authoring — stays outside this skill.
- "Take on faith" applies to the definition, not to the fulfillment: the review answers the fulfillment question with evidence. The seeded `solves-original-problem` question stays and becomes the first question of the review.
- The review loads the agreed baseline (an OpenSpec change when the project uses it; otherwise linked work items, MR context, and human answers), confirms with the human which criteria it will judge against, assesses the implementation against that baseline, marks divergences and risks, and produces a human runbook.
- If the implementation exposes a gap or contradiction in the baseline, `code-review` records it as a baseline doubt and may propose a targeted edit to the existing proposal/design/tasks; it does not re-plan the task or author a new specification.
- Remote actions stay manual and confirmed; the runtime never publishes.

Scope direction, not final: cut or demote the panel poll and mandatory multi-critic arbitration, the OCR critic, code suggestions and patches as the default, the decision/render/prose pipeline, repair paths and legacy v2 commands, SemVer and labels as default review content, and the 37-command surface. Make clean and incremental runs first-class. Keep exact-snapshot collection, freshness, the context baseline, and the runbook.

Open: runtime role, independent-review depth, OpenSpec discovery, local WIP mode, the final cut list.

## Capabilities

### New Capabilities

None yet — the capability spec is drafted after the open questions in `design.md` are decided.

### Modified Capabilities

None.

## Impact

`skills/code-review`, `apps/reviewmatic` (together with `spec-reviewmatic`), the shared references it materializes, skill relations (`code-simplify`, `humanize`, `release-review`, `task-prepare`), and `docs/reference/code-review.md` with its Russian mirror.
