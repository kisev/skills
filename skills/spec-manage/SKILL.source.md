---
name: spec-manage
description: >-
  Create specs, describe an existing project, update agreed contracts as behavior changes, or review specs against implementation. Infer spec-init, spec-onboard, spec-update, or spec-review from intent and evidence. Use spec-update for the canonical part of an authorized implementation change; keep code and user documentation in their own steps. Activate yourself after completing an authorized change that alters material behavior, compatibility, or a security boundary when specs/ exists; this trigger is owned by the skill and needs no project instructions. Russian discovery terms: спецификация проекта, обновить спецификацию, проверить спецификацию.
license: MIT
metadata:
  author: "Kirill Sevriugin"
  source: "https://kisev.github.io/skills"
---

# spec-manage

Before asking the user, apply `references/question-guidelines.md`.

Follow `references/workflow.md`. Apply `references/language-policy.md` to conversation and reports, not to the independently declared language of canonical `specs/` prose. Preserve exact code, commands, paths, IDs, JSON fields, and quotations.

Apply `references/interaction-contract.md` for evidence and mutation rules.

Apply `references/validation.md` as the linking reference directs.

Apply `references/consolidation.md` as the linking reference directs.

Apply `references/architecture.md` as the linking reference directs.

Apply `references/requirements.md` as the linking reference directs.

Apply `references/onboarding.md` as the linking reference directs.

Apply `references/canonical-contract.md` as the linking reference directs.

Apply `references/content-states.md` as the linking reference directs.

Apply `references/minimal-example.md` as the linking reference directs.

Apply `references/documentation-review.md` for documentation impact review.

When the target project contains `openspec/`, read `references/openspec.md` for the OpenSpec coexistence map before acting on `openspec/` artifacts; it bounds what this skill writes there.

Apply `references/auditing.md` as the linking reference directs.

Apply `references/adr.md` as the linking reference directs.

Apply `references/interviewing.md` for spec-init and spec-onboard
interviews.
