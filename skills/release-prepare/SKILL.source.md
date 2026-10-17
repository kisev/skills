---
name: release-prepare
description: >-
  Prepare one stable GitLab release runbook from an exact tag-to-head
  inventory, with SemVer rationale, release notes, announcement, illustration
  prompt, and exactly bound manual glab commands. Use when the user asks to
  prepare a stable release from an exact release MR.
  Russian discovery terms: подготовить релиз.
license: MIT
metadata:
  author: "Kirill Sevriugin"
  source: "https://kisev.github.io/skills"
  inspired-by: "openchamber/openchamber@d1fc27c86f258436e2ac748204e8db9bc9c2878f (MIT © Bohdan Triapitsyn)"
---

# release-prepare

Before any other work in the first session, run `python3 scripts/check_environment.py` from the skill directory and show its output: it prints one OK/FAIL line per external tool from `references/requirements.json` (glab) with the copy-ready install command for every failure. It installs nothing and makes no network call; never install a tool automatically, print the command for the user.

Before asking the user, apply `references/question-guidelines.md`.

Follow `references/workflow.md`. Apply `references/language-policy.md` for user-facing prose. Preserve exact code, commands, paths, IDs, JSON fields, and quotations.

The one-page map of the release chain — every stage from the release MR evidence through finalize, rebind, and the post-merge refresh — is the repository page `docs/reference/release-prepare.md`.
