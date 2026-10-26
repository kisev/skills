---
name: code-simplify
description: >-
  Keep code necessary while coding and audit one explicitly requested scope
  for unnecessary complexity, report-only. Use when the user asks to simplify
  code, remove unnecessary complexity, or audit complexity in a named scope;
  the passive prevention ladder applies to the current change without
  scanning any repository. Never cancel a clarification or confirmation gate.
  Do not trigger on prose or text simplification, which belongs to
  asd-ste100, humanize, and eli5; merge-request reviews route to code-review
  and specification audits route to spec-manage.
  Russian discovery terms: "упростить код", "упрощение кода", "аудит сложности кода".
license: MIT
metadata:
  author: "Kirill Sevriugin"
  source: "https://kisev.github.io/skills"
---

# code-simplify

Before asking the user, apply `references/question-guidelines.md`.

Follow `references/workflow.md`. Apply `references/language-policy.md` for user-facing prose. Preserve exact code, commands, paths, IDs, JSON fields, and quotations.

Apply `references/simplification-criteria.md` for the optional
simplification criteria.
