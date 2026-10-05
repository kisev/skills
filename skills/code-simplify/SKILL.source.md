---
name: code-simplify
description: >-
  Keep code necessary: while coding, apply the passive prevention ladder
  (necessity, existing code, standard library, native platform, installed
  dependency, one line, minimum) to the current change without scanning any
  repository; a targeted caller search by exact name for changed code is part
  of the change, and a conscious cut records a SIMPLIFY debt marker (ceiling
  and upgrade trigger) in the same edit. On an explicit request, audit one
  scope for unnecessary complexity and report ranked one-line findings tagged
  delete, stdlib, native, reuse, yagni, or shrink, report-only, after a usage
  search including dynamic references before any delete, plus a separate
  debt-marker registry section. Never cancel a clarification or confirmation
  gate. Do not trigger on prose or text simplification, which belongs to
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

Follow `references/workflow.md` when it is present. Apply `references/language-policy.md` for user-facing prose. Preserve exact code, commands, paths, IDs, JSON fields, and quotations.
