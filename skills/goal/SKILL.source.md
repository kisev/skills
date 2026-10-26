---
name: goal
description: >-
  Prepare a read-only structured goal of at most 4000 characters as an
  assignment for an LLM agent, not a human-facing work item. Use when the
  next executor is an LLM agent and the assignment must be a verifiable
  read-only goal, not a human-facing work item.
  Russian discovery terms: проверяемая цель.
license: MIT
metadata:
  author: "Kirill Sevriugin"
  source: "https://kisev.github.io/skills"
  inspired-by: "openchamber/openchamber@d1fc27c86f258436e2ac748204e8db9bc9c2878f (MIT © Bohdan Triapitsyn, writing-for-agents by Matt Pocock)"
---

# goal

Before asking the user, apply `references/question-guidelines.md`.

Follow `references/workflow.md`. Apply `references/language-policy.md` for user-facing prose. Preserve exact code, commands, paths, IDs, JSON fields, and quotations.

Apply `references/clarity-rules.md` for the rewrite-preservation rules.

Apply `references/writing-for-agents.md` for wording rules and pointers.

Apply `references/work-item-contract.md` for the work-item contract.
