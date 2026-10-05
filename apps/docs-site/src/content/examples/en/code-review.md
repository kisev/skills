---
skill: code-review
title: Reviewing local WIP before a push
order: 10
prompt: |
  Review my current working tree before I push.
steps:
  - title: Reads the uncommitted diff
    detail: |
      Builds the working tree view from `git status` and `git diff`, mapping
      every hunk to the files and behaviors it touches.
  - title: Checks behavior, not style
    detail: |
      Looks for concrete risks: error paths, concurrency, input validation,
      compatibility, and missing regression coverage.
  - title: Returns a verdict with findings
    detail: |
      Every finding carries a severity and a minimal remediation; the review
      stays read-only and applies no fixes.
artifacts:
  - label: Review report (excerpt)
    language: markdown
    content: |
      ## Findings

      1. **major** - `flushQueue()` swallows rejections: the `catch` block logs
         and continues, so a failed delivery is retried forever. Apply backoff
         and surface the failure to the caller.
      2. **minor** - `MAX_RETRIES` is read at module load, so tests cannot
         shrink it. Read it inside `deliver()` or inject it.

      ## Verdict

      Request changes: fix the retry loop before pushing; the test hook is
      recommended but optional.
limitations: Read-only. Reviews one working tree or merge request at a time and never amends code, stages files, or pushes.
---

The reviewer stays inside the agreed scope: it flags risks in the change
itself and records agreed prior decisions as follow-ups instead of blocking
on them.
