---
name: commit-msg
description: >-
  Generate one concise commit message from local changes, following the
  repository's established language and format. Use only for commit messages,
  not merge request descriptions or release announcements.
  Russian discovery terms: сообщение коммита.
license: MIT
metadata:
  author: "Kirill Sevriugin"
  source: "https://kisev.github.io/skills"
---

# commit-msg

Before any other work in the first session, run `python3 scripts/check_environment.py` from the skill directory and show its output: it prints one OK/FAIL line per external tool from `references/requirements.json` (git) with the copy-ready install command for every failure. It installs nothing and makes no network call; never install a tool automatically, print the command for the user.

Before asking the user, apply `references/question-guidelines.md`.

Follow `references/workflow.md`. Apply `references/language-policy.md` for user-facing prose. Preserve exact code, commands, paths, IDs, JSON fields, and quotations.
