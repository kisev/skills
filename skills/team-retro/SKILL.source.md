---
name: team-retro
description: >-
  Prepare an evidence-based team retrospective, monthly delivery review,
  report, or presentation from a private team profile; it collects its own
  planning and delivery evidence, unlike briefing. Use when the team runs a
  retrospective or monthly delivery review, or needs a report or presentation
  from its own profile.
  Russian discovery terms: ретро, итоги месяца, месячный отчёт, презентация команды.
license: MIT
metadata:
  author: "Kirill Sevriugin"
  source: "https://kisev.github.io/skills"
---

# team-retro

Before any other work in the first session, run `python3 scripts/check_environment.py` from the skill directory and show its output: it prints one OK/FAIL line per external tool from `references/requirements.json` (glab) with the copy-ready install command for every failure. It installs nothing and makes no network call; never install a tool automatically, print the command for the user.

Before asking the user, apply `references/question-guidelines.md`.

Read `references/team-profile-workflow.md`, then follow
`references/workflow.md`. Apply `references/language-policy.md` for user-facing
prose. Preserve exact code, commands, paths, IDs, JSON fields, and quotations.
