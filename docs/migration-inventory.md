# Migration Inventory

[Русский](ru/migration-inventory.md)

## Current Release

The current exact portable source is
`https://github.com/kisev/skills/tree/v2.0.4`. The optional integration package
is `@kisev/skills-opencode@2.0.4`. Latest source is selected separately with
`kisev/skills`.

## Active Portable Skills

There are exactly 29 active portable skills:

`agents-md`, `askme`, `ast-grep`, `code-explain`, `code-review`, `commit-msg`,
`docs-prepare`, `docs-review`, `doit`, `goal`, `humanize`, `lsp-report`,
`mattermost`, `mr-prepare`, `release-prepare`, `release-review`, `rtk`,
`skill-improve`, `slides-prompts-prepare`, `spec-manage`, `stopit`, `summary`,
`task-prepare`, `task-review`, `task-triage`, `team-retro`, `team-roadmap`,
`team-sprint-close`, and `team-sprint-start`.

The source, build, and distribution inventories contain the same self-contained
skills. Generated shared files are declared by `shared/manifest.json` and checked
byte-for-byte.

## Portable Cleanup Records

The current migration inventory has exactly these eight portable records. It
does not contain a portable `multi-run` record.

| Retired name | Current replacement |
| --- | --- |
| `attempt` | None |
| `schedule` | None |
| `usage` | None |
| `overview` | None |
| `project-spec` | `spec-manage` |
| `skill-improver` | `skill-improve` |
| `walkthrough` | `code-explain` |
| `team-workflow` | `team-sprint-start`, `team-sprint-close`, `team-retro`, `team-roadmap`, `slides-prompts-prepare` |

The `skills` CLI `update` operation does not prune renamed or deleted skills.
Codex-only cleanup removes these exact names explicitly with the pinned CLI.
OpenCode or shared installations may also remove them explicitly, or use package
reconcile only when exact ownership can be proved.

## Current OpenCode Surface

The current package inventory has 33 commands: one per active skill plus
`/capabilities`, `/doctor`, `/reconcile`, and `/agent-profiles`. The package tool
`route` remains available without a slash command.

The six fixed agents are `manager`, `architect`, `mapper`, `worker`, `review`, and
`critic`. The selectable plugin wrappers are `rules-injector`, `rtk`, and
`zed-bell`. Package tools are `capabilities`, `route`, `doctor`, `agent_profiles`,
and `reconcile`.

## Ownership and Archive

Confirmed reconcile and uninstall archive only exact-owned assets before
removing deployed copies. Modified, user-owned, unknown, unsafe, and ambiguous
entries remain unchanged as findings or conflicts. Worktrees and runtime state
are preserved. The archive supports transactional rollback and read-only
inspection through `doctor`; no archive restore or purge command is provided.

## Machine-Readable Sources

Exact names, replacements, historical hashes, and source metadata are in
`packages/opencode/assets/migration-inventory.json`. Active package surfaces are
in `packages/opencode/src/catalog.ts`; generated shared-copy declarations are in
`shared/manifest.json`.
