---
name: humanize
description: >-
  Edit user-facing prose into direct, natural language while preserving
  meaning, exact tokens, and the author's voice. Load only on an explicit
  invocation: a direct user request including the /humanize command, or an
  explicit text-preparation step of another skill's workflow. Drafting an
  ordinary reply, status, or explanation never activates this skill by itself.
  Follow the language of the latest request.
  Russian discovery terms: естественный русский текст.
license: MIT
metadata:
  author: "Kirill Sevriugin"
  source: "https://kisev.github.io/skills"
  inspired-by: "openchamber/openchamber@d1fc27c86f258436e2ac748204e8db9bc9c2878f (MIT © Bohdan Triapitsyn, communication-style by poteto)"
---

# humanize

## Activation

Load this skill only on an explicit invocation:

- The user asks for it directly, including the `/humanize` command or naming
  the skill in a request to write or edit prose.
- Another skill's workflow reaches an explicit text-preparation step that
  applies `humanize`.

Writing an ordinary reply, status, or explanation is not an invocation: write
such text normally and do not load these rules by default. The strict rules in
this skill govern only text produced under an invocation; they never become a
standing profile or a global default.

Before asking the user, apply `references/question-guidelines.md`.

Follow `references/workflow.md` when it is present. Apply
`references/language-policy.md` for user-facing prose. Preserve exact code,
commands, paths, IDs, JSON fields, and quotations. For the full editing
catalog with before/after examples, read `references/patterns.md`.
