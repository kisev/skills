# Migration Inventory

[Русский](ru/migration-inventory.md)

This repository ships independent portable skills through `npx skills`.

| Skill          | Mode            | Purpose                                     |
| -------------- | --------------- | ------------------------------------------- |
| `askme`        | read-only       | Clarify a task or decision.                 |
| `doit`         | previewed write | Perform a scoped engineering change.        |
| `project-spec` | explicit modes  | Maintain canonical specifications.          |
| `task-prepare` | local plan      | Prepare a GitLab issue without publication. |
| `code-review`  | read-only       | Review a GitLab MR or local WIP.            |
| `schedule`     | confirmed write | Define disabled-by-default schedules.       |

Skills do not inherit host runtime state or configuration. `work-item/v1` is a
versioned contract for `askme`, `task-prepare`, `task-review` and `goal`.
`task-triage` remains a separately scoped read-only workflow.

Shared stdlib code is materialized from `shared/references/`; the optional
`packages/opencode/` package does not ship copied skills.
Retired public entries require exact SHA-256 validation.
The `agent_profiles` adapter is package-only; machine-readable public-surface
history is in `packages/opencode/assets/migration-inventory.json`.
