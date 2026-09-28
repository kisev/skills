# Documentation Review Workflow

The input is a path or scope. Without one, review the complete user-facing documentation set. An explicit path or section narrows the scope. If it is in `specs/`, route that part to `spec-manage` in `spec-review` mode. Do not change the repository, documents, or external systems. Use `references/documentation-review.md` for private evidence, incremental reuse, impact selection, and a full-review independent critic. Report findings in chat and never publish them.

Identify the target reader and purpose in scope. Check claims, commands, APIs, configuration, and examples against source, tests, canonical specifications, and repository instructions. Check prerequisites, sequence, error consequences, compatibility, stale links, and terminology. Report only confirmed findings, each with severity, exact evidence, consequence, and minimal correction. If none exist, say so briefly and list unverified boundaries.

## Boundary

- Input is a path or area. Without either, review the complete user-facing documentation set in the current project and report any unchecked boundaries explicitly.
- If the area is in `specs/`, use `spec-manage` in `spec-review` mode.
- Do not modify the repository, documents, external systems, or publication targets. Private review state is permitted only under the shared review contract.
- Output findings only in chat; do not publish them to external systems.

## Review

1. Determine the target reader and the purpose of documentation in the specified boundary.
2. Resolve the expected language set from the explicit user request, project rules, or the agent's global rules. Check that every declared mirror exists and that machine tokens (commands, paths, flags, IDs, JSON fields) are byte-identical across mirrors.
3. Check agent annotations: `audience` is declared, `agent` hints still match actual commands and behavior, frontmatter and agent sections are identical across language mirrors, and no executable contract hides in user prose instead of the canonical specification or an explicit agent section.
4. Check claims, commands, APIs, configuration, and examples against source code, configuration, and repository instructions.
5. Check prerequisites, order of actions, effects of errors, compatibility, stale links, and terminological consistency.
6. Report only confirmed findings. For each, state severity, precise evidence, consequence, and the minimal fix.
7. If there are no findings, state that briefly and list unverified boundaries.

## Memory integration

Before reviewing, search personal memory (`memory_search` tool or
`memomatic search`) for this project's documentation conventions; personal
entries inform the review but must never be quoted into shared documents.

After reporting the findings, offer one memory drop of the durable lesson
(recurring documentation failure, convention drift) and run it after user
confirmation:

```shell
python3 scripts/memomatic_inbox.py drop --source docs-review \
  --project PROJECT --text "Durable documentation lesson in one sentence."
```

The drop is queued for the next `memomatic process` pass; when the memomatic
inbox is absent the command reports `skipped` and the workflow continues
unchanged.
