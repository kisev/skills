---
name: code-review
description: >-
  Review one GitLab merge request or local WIP for concrete risks and proportionate fixes, preserving agreed scope and prior decisions in follow-ups. Include GitLab labels, SemVer, and manual publication commands for remote reviews. Russian discovery terms: ревью кода.
license: MIT
metadata:
  author: "Kirill Sevriugin"
  source: "https://kisev.github.io/skills"
---

# code-review

The executable runtime is the external npm package `@kisev/reviewmatic` (bin `reviewmatic`); install it once like `glab`. Every runner command in this archive is that bin.

Review preparation depends on the reviewmatic backend. Finished runbook commands
execute directly through `glab` without reviewmatic. Only the interactive TUI is
experimental; backend collection, repair, refresh and finalization remain supported.

Before asking the user, apply `references/question-guidelines.md`.

Follow `references/workflow.md` when it is present. Apply `references/language-policy.md` for user-facing prose. Preserve exact code, commands, paths, IDs, JSON fields, and quotations.
