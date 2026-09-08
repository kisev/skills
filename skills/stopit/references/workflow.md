# Workflow

## Boundary

- Create a new file in the operating system temporary directory, not in the
  repository.
- Do not change the repository, `.gitignore`, Git state, or external systems.
- Do not copy logs, secrets, personal data, or large context. Use a redacted
  summary and exact references to existing artifacts, paths, or SHA values.

## Procedure

1. Treat the supplied focus as the purpose of the next session.
2. Collect only verifiable facts from the conversation, repository, and existing
   artifacts. Separate decisions from assumptions and unresolved questions.
3. Prepare a new draft. As needed, use the sections `Decisions`, `Current state`,
   `Blockers`, `Next steps`, `Artifacts`, and `Recommended skills`; do not add
   empty sections.
4. Show the complete draft and temporary path, then obtain explicit confirmation
   before writing.
5. After confirmation, create only that temporary file. Briefly report which data
   were summarized or redacted and which references were retained instead of being
   copied.

## Result

- The handoff is usable by the next session without hidden state.
- Completed, current, next, and blocking work are explicitly separated.
- There are no Git or external-system changes.
