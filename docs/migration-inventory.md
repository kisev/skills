# Migration Inventory

[Русский](ru/migration-inventory.md)

This stage targets release `2.0.0` from source ref
`5f09d504758b0e99ad9c0306df796411fbcf0f4a`. The public surface is exact and has
no aliases.

## Active Skills

`agents-md`, `askme`, `ast-grep`, `code-explain`, `code-review`, `commit-msg`,
`docs-prepare`, `docs-review`, `doit`, `goal`, `humanize`, `lsp-report`,
`mattermost`, `mr-prepare`, `release-prepare`, `release-review`, `rtk`,
`skill-improve`, `slides-prompts-prepare`, `spec-manage`, `stopit`, `summary`,
`task-prepare`, `task-review`, `task-triage`, `team-retro`, `team-roadmap`,
`team-sprint-close`, `team-sprint-start`.

The source, build, and distribution inventories each contain exactly these 29
self-contained skills. Generated shared files are declared by
`shared/manifest.json` and checked byte-for-byte.

## Structural Migration

| Retired path | Target | Source SKILL.md SHA-256 |
| --- | --- | --- |
| `skills/project-spec` | `skills/spec-manage` | recorded in machine inventory |
| `skills/skill-improver` | `skills/skill-improve` | recorded in machine inventory |
| `skills/walkthrough` | `skills/code-explain` | recorded in machine inventory |
| `skills/team-workflow` | five fixed skills below | recorded in machine inventory |

Removed without replacement: `skills/attempt`, `skills/schedule`,
`skills/usage`, and `skills/overview`. The team replacements are
`team-sprint-start`, `team-sprint-close`, `team-retro`, `team-roadmap`, and
`slides-prompts-prepare`; each has its own fixed workflow entrypoint and does
not expose a public mode selector.

## Commands

There are exactly 33 commands: one command for each active skill, loading only
the same-named skill and passing `$ARGUMENTS`, plus `/capabilities`, `/doctor`,
`/reconcile`, and `/agent-profiles`. The package tool `route` remains available
without a slash command. No action or mode aliases are shipped.

Retired `2.0.0` assets are reported as `archive-pending`. Reconcile preserves
their bytes and apply rejects irreversible cleanup until the archive lifecycle
stage. Archive, restore, and purge are out of scope.

Machine-readable details, including source ref, versions, hashes, replacements,
and `aliases: []`, are in `packages/opencode/assets/migration-inventory.json`.
