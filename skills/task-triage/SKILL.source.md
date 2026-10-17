---
name: task-triage
description: >-
  Triage one GitLab issue or a bounded issue collection into persistent
  read-only analysis, release milestones, priorities, dependencies, and
  manual update commands. Use when the user asks to triage a GitLab issue or
  a bounded collection of issues.
  Russian discovery terms: разобрать задачу, провести триаж задач.
license: MIT
metadata:
  author: "Kirill Sevriugin"
  source: "https://kisev.github.io/skills"
  inspired-by: "openchamber/openchamber (MIT © Bohdan Triapitsyn); solution 37, blocks 1-2"
---

# task-triage

Before any other work in the first session, run `python3 scripts/check_environment.py` from the skill directory and show its output: it prints one OK/FAIL line per external tool from `references/requirements.json` (git, glab) with the copy-ready install command for every failure. It installs nothing and makes no network call; never install a tool automatically, print the command for the user.

Before asking the user, apply `references/question-guidelines.md`.

Follow `references/workflow.md`. Apply `references/language-policy.md` for user-facing prose. Preserve exact code, commands, paths, IDs, JSON fields, and quotations.
