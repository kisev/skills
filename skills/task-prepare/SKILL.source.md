---
name: task-prepare
description: >-
  Prepare a self-contained task or agreed GitLab task set, apply shared
  review and scoped release planning, and produce a local Markdown plan with
  manual glab commands. Use when the user asks to prepare a task, an issue,
  or an agreed task set for execution or GitLab publication.
  Russian discovery terms: подготовить задачу, подготовить issue.
license: MIT
metadata:
  author: "Kirill Sevriugin"
  source: "https://kisev.github.io/skills"
---

# task-prepare

Before any other work in the first session, run `python3 scripts/check_environment.py` from the skill directory and show its output: it prints one OK/FAIL line per external tool from `references/requirements.json` (glab) with the copy-ready install command for every failure. It installs nothing and makes no network call; never install a tool automatically, print the command for the user.

Before asking the user, apply `references/question-guidelines.md`.

Follow `references/workflow.md`. Apply `references/language-policy.md` for user-facing prose. Preserve exact code, commands, paths, IDs, JSON fields, and quotations.
