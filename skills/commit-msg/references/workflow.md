# Commit Message

## Algorithm

1. Verify that the current directory is inside a Git worktree. If it is not, report that.
2. Read every applicable `AGENTS.md` for repository and target scope, then inspect commitlint/configuration and up to the 20 most recent commit subjects. Obtain `git status --short`, `git diff --cached --stat`, and `git diff --cached`.
3. If staged changes exist, formulate the message only from them. Unstaged and untracked changes will not be included in this commit.
4. If there are no staged changes, obtain `git diff --stat` and `git diff`, then analyze the tracked diff and untracked files as the proposed set for a future commit. Read the contents of untracked files selectively; do not open large, binary, or likely secret files without reason.
5. If the user explicitly specified a path set or asked to consider staged and unstaged changes together, use only that scope.
6. Verify that the selected changes form one logical change. If they contain unrelated outcomes, stop and concisely report that the set should be split instead of omitting changes from the message. Otherwise, determine the outcome and its user-facing or technical effect.
7. Determine the message language and format from applicable repository instructions, commit configuration, and a clearly established pattern in the inspected history. If these sources prescribe conflicting requirements, stop and concisely report the mismatch instead of choosing a priority.
8. Output exactly one line containing the commit message, `no changes to commit`, a concise repository-convention mismatch report, or a concise non-atomic-change report.

## Rules

- If the repository sources establish no message format, use Conventional Commit: `type[optional scope][!]: description`.
- When using Conventional Commit, choose `type` by the actual effect; do not invent a scope if it does not help.
- If the repository sources establish no wording style, write the descriptive subject in imperative mood, omit the trailing period, and ensure it completes `If applied, this commit will ...` after any Conventional Commit prefix is removed.
- Target at most 50 characters, with a hard limit of 72, unless the repository defines another limit.
- Do not add file names, paths, task identifiers, or empty words such as `changes`.
- Keep the subject meaningful on its own; reject vague descriptions such as `update stuff`, `fix bug`, or `misc changes`.
- Do not combine unrelated changes through an invented shared formulation or omit less significant selected changes to force one message.
- Describe even formatting and typos by effect, for example `fix typo in error message`.
- Do not run `git add`, `git commit`, or modify the worktree.
