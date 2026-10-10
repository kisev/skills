---
name: skill-doctor
description: >-
  Diagnose skill usage of the current session on an explicit request. Use
  only when the user explicitly asks to diagnose this session's skill usage;
  it never triggers by itself and never audits skills without session
  history.
  Russian discovery terms: продиагностировать скиллы, разбор сессии, ошибки скиллов, баг-репорт навыка.
license: MIT
metadata:
  author: "Kirill Sevriugin"
  source: "https://kisev.github.io/skills"
  inspired-by: "openchamber/openchamber@d1fc27c86f258436e2ac748204e8db9bc9c2878f (MIT © Bohdan Triapitsyn, writing-for-agents by Matt Pocock)"
---

# skill-doctor

Before asking the user, apply `references/question-guidelines.md`.

Follow `references/workflow.md`. Apply `references/language-policy.md` for user-facing prose. Preserve exact code, commands, paths, IDs, JSON fields, and quotations.
