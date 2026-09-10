# Engineering Task Workflow

Read `references/interaction-contract.md` and follow its lifecycle. Work in the current worktree and branch by default; create a sibling isolated worktree only on explicit request. Before writing, prepare a private content-addressed preview artifact and show only TLDR: objective, exact base SHA, scope, checks, risks, path, and SHA-256 digest. Do not print the full diff. Obtain Confirmation of the exact mutation. `git add`, `commit`, `rebase`, `push`, `merge`, `tag`, `release`, and external publication are allowed only when that exact action is included in the approved plan; external publication and history rewrite require separate confirmations. Stage only paths from this workflow. Do not change unfamiliar or user-owned changes; on a direct conflict stop and ask. Do not require a particular host, state, question tool, agent, task, or specification command.

Read applicable `AGENTS.md`, task, available requirements, analogous implementation, and tests; check `git status`, base SHA, and branch. Classify as fix, feature, refactor, prototype, or diagnosis without treating assumptions as facts. Select the needed skills, then prepare an exact plan containing write set, checks, evidence requirements, and risk boundaries. Do not infer permission from a general request to finish the work. Group confirmations by independent risk, not by file, and execute only confirmed plan actions. Prepare and present the preview before the first write. Implement small vertical slices, add a test for observable contract or material risk, and run focused checks after slices. In diagnosis, reproduce the symptom and prove the cause; otherwise return evidence and blocker, not a guessed fix. In a prototype, test one runnable question, list simplifications, and do not automatically propose merge. After implementation, report `git status`, checks, and limitations; prepare a separate compact commit preview and request its Confirmation, leaving changes in place if rejected.

Before a requested worktree, show future path, branch, and base ref. Do not carry uncommitted source-checkout changes, delete a worktree without separate confirmation, or create hidden state/ownership storage. Resolve conflicts in this order: safety and confirmation, explicit user request, repository pipeline, then local composition.

## Boundary

- Read `references/interaction-contract.md` and follow its lifecycle.
- By default, work in the current worktree and current branch. Create an adjacent isolated worktree only upon the user's explicit request.
- Before writing, prepare a private content-addressed preview artifact. Show only its TLDR in chat: goal, exact base SHA, scope, checks, risks, path, and SHA-256 digest; do not print the full diff. Obtain Confirmation for the exact mutation.
- `commit`, `rebase`, `push`, `merge`, `tag`, and `release` are allowed only as exact operations in the approved plan; each requires its applicable confirmation. `git add` and `git commit` require separate confirmation after the final diff; add only paths from this workflow to the index.
- Do not modify unfamiliar or user changes. On a direct conflict, stop and ask how to proceed.
- Do not require a specific host, its state, question tools, agents, tasks, or separate specification commands. If a question is needed, ask it in chat or through the host's standard mechanism.
- `doit` is the only coordinator for evidence -> plan -> confirmation -> execution -> checks -> report. OpenCode adapters may route work, but may not implement a second coordinator lifecycle.
- Resolve conflicting reports against their exact evidence references, not by vote; an unsupported or unresolved claim remains blocked and requires fresh evidence.
- Documentation and quick requests are handled here; they are not routing destinations. Any VCS operation is permitted only when named exactly in the approved plan, with separate publication and history-rewrite confirmations.

## Work Order

1. Read applicable `AGENTS.md`, the task, requirements documents when present, similar implementation, and tests. Check `git status`, the base SHA, and the current branch.
2. Classify the task as a fix, feature, refactoring, prototype, or diagnosis. Do not call an assumption a proven fact.
3. Prepare and briefly present a preview, then wait for Confirmation before the first write.
4. Implement in small vertical slices. Add a test for an observable contract or material risk and run targeted checks after slices.
5. In diagnosis, first reproduce the symptom and prove the cause. If that fails, return evidence and a blocker instead of a presumed fix.
6. In a prototype, verify one executable question, explicitly list simplifications, and do not propose merge automatically.
7. After implementation, issue a separate report with `git status`, checks, and limitations. Prepare a separate compact commit preview and request its Confirmation; on rejection, leave changes in place.

## Worktree on Request

Before creating a worktree, show its future path, branch, and base ref. Do not transfer uncommitted changes from the source checkout. Do not remove a worktree without separate confirmation. Use the repository's standard Git lifecycle; do not create hidden state or ownership storage.

## Decision Priority

When recommendations conflict, use this order: safety and confirmation, the user's explicit request, the repository pipeline, then local composition.
