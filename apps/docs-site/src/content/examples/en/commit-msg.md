---
skill: commit-msg
title: One message for a mixed staging change
order: 10
prompt: |
  Look at my staged changes and write the commit message.
steps:
  - title: Inspect the staged diff and recent history
    detail: |
      Runs `git diff --cached --stat` and `git log --oneline -8` to learn what
      changed and which conventions the repository already follows.
  - title: Draft the subject from the dominant change
    detail: |
      The diff touches one parser function and its regression tests, so the
      subject names the behavior fix instead of listing files.
  - title: Print the message only
    detail: The skill never runs `git commit`; it prints the message for review.
artifacts:
  - label: Commit message (printed to the terminal)
    language: text
    content: |
      fix: tolerate empty frontmatter blocks in skill sources

      Trim leading document separators before YAML parsing so a source file
      that starts with a comment-only header still validates, and cover the
      case with a parser regression test.
limitations: Produces one message per invocation and never creates the commit. It targets commit messages only; merge request descriptions are out of scope.
---

The repository in this example keeps a linear history with `fix:` and `feat:`
subjects under 72 characters, so the skill matches the dominant convention
instead of inventing its own format.
