---
skill: mr-review
title: Reviewing a merge request against its task
order: 10
prompt: |
  Review this merge request: https://gitlab.example.com/group/project/-/merge_requests/7
steps:
  - title: Collects the exact context
    detail: |
      Reads the merge request, diff, discussions, pipelines, and linked issues
      read-only, bound to the exact base, start, and head revisions.
  - title: Confirms the task baseline
    detail: |
      Asks one startup round: the OCR reviewer aliases and effort, and the
      goal and acceptance criteria from the linked issues and the description.
  - title: Runs the OCR engine
    detail: |
      Runs one OpenCodeReview process per selected alias, in parallel, then
      merges duplicates and conflicting severities with recorded reasons.
  - title: Answers whether the task is solved
    detail: |
      Produces the runbook verdict with evidence, the OCR runs, the checks,
      and one draft-note block that starts with a head check.
artifacts:
  - label: Runbook (excerpt)
    language: markdown
    content: |
      ## Task fulfillment

      **Verdict:** partially. The limit applies per IP; the per-user
      criterion is uncovered.

      ## OCR runs

      | Alias | Provider | Model | Effort | Mode | Exit | Findings |
      | - | - | - | - | - | - | - |
      | fast | openai | gpt-5 | medium | parallel | 0 | 2 |
      | deep | anthropic | claude-opus-5 | high | parallel | 0 | 3 |

      ## Checks

      - Pipeline: passed.
      - Failed jobs: none.
limitations: Read-only. Creates GitLab draft notes only; the human edits and publishes them in the UI.
---

The reviewer answers one question: does this change solve the task it was made
for? Findings come only from the OCR runs, and the human publishes the review.
