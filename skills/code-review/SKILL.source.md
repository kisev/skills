---
name: code-review
description: >-
  Review one GitLab merge request or local WIP for concrete risks and proportionate fixes, preserving agreed scope and prior decisions in follow-ups. Include GitLab labels, SemVer, and manual publication commands for remote reviews. Russian discovery terms: ревью кода.
license: MIT
metadata:
  author: "Kirill Sevriugin"
  source: "https://kisev.github.io/skills"
  inspired-by: "openchamber/openchamber (MIT © Bohdan Triapitsyn); solution 37, blocks 1-2; blocks 3-4 pinned at openchamber/openchamber@d1fc27c86f258436e2ac748204e8db9bc9c2878f"
---

# code-review

The runtime is the Python 3.12+ application in `apps/reviewmatic`, run ephemerally from Git with `uvx`; it is not published to npm or PyPI and needs no `uv tool install`. Select the same source channel as the skill: an exact `vX.Y.Z` release tag for stable, or the moving `dev` branch for development. Set `REVIEWMATIC_FROM='git+https://github.com/kisev/skills.git@<ref>#subdirectory=apps/reviewmatic'` once and run every CLI command, including returned continuation actions, as `uvx --from "$REVIEWMATIC_FROM" reviewmatic ...`. Do not rely on a globally installed `reviewmatic` executable.

Drive a remote-MR review through the one-process `reviewmatic run` path. At the start of every review ask the user one poll — the critic composition and the engine of every critic (a model subagent or the mechanical `ocr` CLI) — and record the answer as the run panel selection; attach your recommendation to the poll, and let the user decide. The step-by-step `start-review`/`record-*` flow remains supported as the explicitly marked repair path.

Review preparation depends on the reviewmatic backend. Finished runbook commands
execute directly through `glab` without reviewmatic. Backend collection, repair,
refresh and finalization remain supported; the runtime has no interactive TUI.

Before asking the user, apply `references/question-guidelines.md`.

Follow `references/workflow.md` when it is present. Apply `references/language-policy.md` for user-facing prose. Preserve exact code, commands, paths, IDs, JSON fields, and quotations.
