# Tasks

## 1. Shared canon

- [ ] 1.1 Add the premortem section (at most three causes with probability,
  impact, and a proposed wording change; independent agent only; `skipped`
  without one) to `shared/references/necessity-doctrine.md` beside the
  work-item machine contract — verification: the section matches the
  `work_item.py` premortem validator semantics
- [ ] 1.2 Add the recommendation-conflict order (safety and confirmation >
  explicit user request > pipeline > layering) to
  `shared/references/question-guidelines.md` — verification: the paragraph
  is in the shared file and absent from every skill-local workflow
- [ ] 1.3 Register `goal/references/necessity-doctrine.md` in
  `shared/manifest.json` and materialize — verification: `task generate`
  then `task generate:check` green; the goal archive contains the doctrine

## 2. Skill text

- [ ] 2.1 askme workflow: align step 3 with the canon frontier — the
  prerequisite precedes its dependents, independent questions are not
  serialized behind it — verification: structure lint green; the "alone"
  over-serialization wording is gone
- [ ] 2.2 askme workflow: replace the "Composition Protocol" section with a
  premortem delegation to the necessity doctrine (conflict order now lives
  in the question guidelines) and drop the duplicate "Necessity before
  implementation choices" section — verification: structure lint green; no
  rule remains duplicated between the workflow and the shared references
- [ ] 2.3 askme workflow: ambiguous invocation context asks exactly one
  bounded mode question and stops only on an unresolved answer —
  verification: structure lint green; the invocation-boundary section names
  the clarification and the unresolved stop
- [ ] 2.4 goal workflow: replace the inline premortem paragraph with a
  delegation to the materialized necessity doctrine — verification:
  structure lint green; goal's archive stays self-contained

## 3. Verification

- [ ] 3.1 Run the audit of every spec requirement against the edited skill
  text and shared references — verification: each requirement maps to
  workflow or canon text, or the diverging side is fixed and recorded
- [ ] 3.2 Run the offline corpus checks — verification: `task eval:check`
  green; the askme trigger, near-miss (both languages), and command-contract
  scenarios pass with unchanged selection expectations
- [ ] 3.3 Run the full pressure run for askme per
  `docs/how-to/portable-skills.md` (skill text changed) — verification:
  baseline-versus-wording report with at least five repeats per side and
  the no-guidance control
- [ ] 3.4 Run the full pressure run for goal (its workflow text changed) —
  verification: same pressure contract as 3.3
- [ ] 3.5 Run the repository gates — verification: `task check:core` green
  plus `task locale:check` when documentation pairs changed

## 4. Archive

- [ ] 4.1 Validate and archive the change — verification: `openspec
  validate spec-askme --strict` passes and archiving creates
  `openspec/specs/askme/spec.md` from the delta
