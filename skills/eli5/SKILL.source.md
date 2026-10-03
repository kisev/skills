---
name: eli5
description: >-
  Explain a complex concept in plain language for a reader who lacks the
  field's background. Use when the user asks to "explain simply", "eli5",
  "break it down", or to explain something to a non-specialist; match
  equivalent intent, not just these phrases. Calibrate to the available
  knowledge about the reader instead of assuming a five-year-old audience.
  Keep essential constraints and uncertainty; examples and analogies never
  replace exact conditions. Do not trigger on quoted text or discussion of the
  skill itself. Russian discovery terms: "объясни просто", "объясни на пальцах", "объясни как неспециалисту".
license: MIT
metadata:
  author: "Kirill Sevriugin"
  source: "https://kisev.github.io/skills"
---

# eli5

Before asking the user, apply `references/question-guidelines.md`.

Follow `references/workflow.md` when it is present. Apply `references/language-policy.md` for user-facing prose. Preserve exact code, commands, paths, IDs, JSON fields, and quotations.
