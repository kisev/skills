# Manual GitLab publication

This contract governs every prepared GitLab publication in the task, MR, and
release skills: the agent prepares, the user executes. It extends
`references/gitlab-workflow.md` with the command-execution boundary.

## Read-only preparation

Preparation is read-only for GitLab: the skill and every helper collect
evidence and write local artifacts, but they never execute a publication
command. Never run the generated publication commands, and never create,
update, approve, merge, push, or mutate anything on the target automatically.

## User-executed commands

The agent stops after preparing the plan. The user manually runs each command
at most once and inspects its response before treating the change as executed.
GitLab's GraphQL API answers HTTP 200 even when the request fails: inspect the
`errors` field of every response, plus the new URL, IID, or work item global
ID where the command creates one. After a timeout or lost response, inspect
GitLab before retrying to avoid duplicates. A local file or a previously
displayed command is not publication proof.

## Advisory markers and execution status

After exit zero, each mutation command writes an advisory XDG marker. The
marker does not prove that GitLab reached the expected state and never makes
a retry safe. Regenerated command blocks show `execution-status=not_run` or
`execution-status=run_unverified`; reconcile `run_unverified` actions against
refreshed GitLab evidence before any retry or dependent step, and keep them
visible until that evidence confirms the target state.
