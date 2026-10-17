---
name: ast-grep
description: >-
  Run structural search or confirmed AST rewrites with ast-grep. Use when a
  structural or AST-level code search or rewrite is needed and plain text
  search is not enough.
  Russian discovery terms: структурный поиск.
license: MIT
metadata:
  author: "Kirill Sevriugin"
  source: "https://kisev.github.io/skills"
---

# ast-grep

Before any other work in the first session, run `python3 scripts/check_environment.py` from the skill directory and show its output: it prints one OK/FAIL line per external tool from `references/requirements.json` (ast-grep) with the copy-ready install command for every failure. It installs nothing and makes no network call; never install a tool automatically, print the command for the user.

Before asking the user, apply `references/question-guidelines.md`.

Follow `references/workflow.md`. Apply `references/language-policy.md` for user-facing prose. Preserve exact code, commands, paths, IDs, JSON fields, and quotations.
