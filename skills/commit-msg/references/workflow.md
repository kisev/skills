# Commit Message

## Algorithm

1. Verify that the current directory is inside a Git worktree. If it is not, report that.
2. Read every applicable `AGENTS.md` for repository and target scope, then inspect commitlint/configuration and recent repository history. Obtain `git status --short`, `git diff --cached --stat`, and `git diff --cached`.
3. If staged changes exist, formulate the message only from them. Unstaged and untracked changes will not be included in this commit.
4. If there are no staged changes, analyze the tracked diff and untracked files as the proposed set for a future commit. Read the contents of untracked files selectively; do not open large, binary, or likely secret files without reason.
5. If the user explicitly specified a path set or asked to consider staged and unstaged changes together, use only that scope.
6. Determine one outcome and the user-facing or technical effect, using repository rules and history to select the actual message style.
7. Output exactly one line or `no changes to commit`.

## Rules

- Use Conventional Commit: `type[optional scope][!]: description`.
- Choose `type` by the actual effect; do not invent a scope if it does not help.
- Do not add file names, paths, task identifiers, or empty words such as `changes`.
- Do not combine unrelated changes through an invented shared formulation. If one message is impossible, choose the most significant staged effect.
- Describe even formatting and typos by effect, for example `fix typo in error message`.
- Do not run `git add`, `git commit`, or modify the worktree.
