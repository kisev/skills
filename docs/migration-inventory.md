# Migration Inventory

[Русский](ru/migration-inventory.md)

## Current Release

The current portable source is the GitHub Pages stable channel at
`https://kisev.github.io/skills`. Its release metadata identifies the release and
source revision, while `https://github.com/kisev/skills/releases/latest` resolves
the current GitHub Release. The optional integration package is
`@kisev/agentomatic`.

## Active Portable Skills

There are exactly 38 active portable skills:

`agents-md`, `askme`, `ast-grep`, `code-explain`, `code-review`, `commit-msg`,
`docs-prepare`, `docs-review`, `goal`, `humanize`, `mattermost`,
`mattermost-triage`, `mr-prepare`, `release-prepare`, `release-review`, `rtk`,
`skill-improve`, `slides-prompts-prepare`, `spec-manage`, `stopit`, `briefing`,
`task-prepare`, `task-review`, `task-triage`, `taskmatic`, `team-1on1`,
`team-agreements`, `team-feedback`, `team-health`, `team-incident`,
`team-onboarding`, `team-people`, `team-performance`, `team-report`,
`team-retro`, `team-roadmap`, `team-sprint-close`, and `team-sprint-start`.

The authored inventory contains deduplicated definitions; build and distribution
inventories contain the same 38 self-contained skills. Shared files are declared
by `shared/manifest.json`, injected only into `.build/skills`, and checked
byte-for-byte.

## Portable Cleanup Records

The current migration inventory names exactly these eleven retired portable skills. It
does not contain a portable `multi-run` record.

| Retired name | Current replacement |
| - | - |
| `attempt` | None |
| `schedule` | None |
| `usage` | None |
| `overview` | None |
| `doit` | None |
| `lsp-report` | None |
| `project-spec` | `spec-manage` |
| `skill-improver` | `skill-improve` |
| `walkthrough` | `code-explain` |
| `team-workflow` | `team-sprint-start`, `team-sprint-close`, `team-retro`, `team-roadmap`, `slides-prompts-prepare` |
| `people-workflow` | `team-people`, `team-1on1`, `team-feedback`, `team-agreements`, `team-onboarding`, `team-incident`, `team-performance`, `team-report`, `team-health` |
| `summary` | `briefing` |

The `skills` CLI `update` operation detects names deleted upstream and offers to
remove their local copies. Cleanup can also remove these exact names explicitly
with stable `skills@latest` and the same agents and scope as the installation.
The OpenCode package does not inspect or remove portable skills.

## Current OpenCode Surface

The current package inventory has 38 commands, one per active skill. The package
tool `route` remains available without a slash command.

The six fixed agents are `manager`, `architect`, `mapper`, `worker`, `review`, and
`critic`. The selectable plugin wrappers are `rules-injector`, `rtk`, and
`zed-bell`. The only package tool is `route`; administration uses the direct CLI.

## Ownership and Archive

Confirmed reconcile and uninstall archive only exact-owned package assets before
removing deployed copies. Portable skills and their installer lock files remain
outside package ownership. User-owned, unknown, unsafe, and ambiguous entries
remain unchanged as findings or conflicts. Worktrees and runtime state are
preserved. The archive supports transactional rollback and read-only inspection
through `doctor`; no archive restore or purge command is provided.

## Machine-Readable Sources

Exact names, replacements, historical hashes, and source metadata are in
`packages/agentomatic/assets/migration-inventory.json`. Active package surfaces are
in `packages/agentomatic/src/catalog.ts`; portable release metadata is in
`packages/skills/package.json`; build-only shared-file declarations are in
`shared/manifest.json`.
