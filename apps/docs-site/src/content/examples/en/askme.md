---
skill: askme
title: Clarifying a vague feature request
order: 10
prompt: |
  Add pagination to the users endpoint.
steps:
  - title: Checks the repository first
    detail: |
      Finds an existing list helper with offset pagination and a project rule
      against reinventing shared utilities, so the implementation question is
      answered by inspection, not by asking.
  - title: Builds a decision tree
    detail: |
      One decision remains that changes the public API contract: the page
      size policy.
  - title: Asks the smallest useful question
    detail: One question, options with concrete effects, a recommendation - then it waits.
artifacts:
  - label: Interview question (chat)
    language: markdown
    content: |
      **Page size policy** - the endpoint returns up to 50 items today, and
      the choice locks the public contract:

      - **Server-fixed, 50 (Recommended)** - no client parameter to validate
        or document; changing the size later stays a backward-compatible bump.
      - **Client-controlled, 1-100** - flexible for power clients, but you own
        validation, caps, and documentation of every misuse.

      Which policy should the endpoint implement?
limitations: Asks only what cannot be established by inspection; the interview ends with a decision boundary and never implements anything by itself.
---

The skill resolves the minimum it needs: the helper choice never reached the
user because the repository had already answered it.
