# Инвентарь миграции

[English](../migration-inventory.md)

## Текущий выпуск

Текущий portable source - stable channel GitHub Pages:
`https://kisev.github.io/skills`. Его release metadata указывает release и source
revision, а `https://github.com/kisev/skills/releases/latest` открывает текущий
GitHub Release. Optional integration package: `@kisev/skills-opencode`.

## Активные portable skills

Активны ровно 29 portable skills:

`agents-md`, `askme`, `ast-grep`, `code-explain`, `code-review`, `commit-msg`,
`docs-prepare`, `docs-review`, `doit`, `goal`, `humanize`, `lsp-report`,
`mattermost`, `mr-prepare`, `release-prepare`, `release-review`, `rtk`,
`skill-improve`, `slides-prompts-prepare`, `spec-manage`, `stopit`, `briefing`,
`task-prepare`, `task-review`, `task-triage`, `team-retro`, `team-roadmap`,
`team-sprint-close`, `team-sprint-start`.

Authored inventory содержит deduplicated definitions; build и distribution
inventories содержат те же 29 self-contained skills. Shared files объявлены в
`shared/manifest.json`, добавляются только в `.build/skills` и проверяются
byte-for-byte.

## Portable cleanup records

Текущий migration inventory содержит ровно эти восемь portable records. Portable
record `multi-run` в нём отсутствует.

| Retired name     | Current replacement                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------------ |
| `attempt`        | Нет                                                                                              |
| `schedule`       | Нет                                                                                              |
| `usage`          | Нет                                                                                              |
| `overview`       | Нет                                                                                              |
| `project-spec`   | `spec-manage`                                                                                    |
| `skill-improver` | `skill-improve`                                                                                  |
| `walkthrough`    | `code-explain`                                                                                   |
| `team-workflow`  | `team-sprint-start`, `team-sprint-close`, `team-retro`, `team-roadmap`, `slides-prompts-prepare` |

Операция `update` в CLI `skills` не удаляет renamed или deleted skills. Cleanup
удаляет эти exact names явно через stable `skills@latest` с теми же agents и scope,
что и installation. Package installation и reconcile не заменяют portable source
rebind или cleanup flow.

## Текущая поверхность OpenCode

Текущий package inventory содержит 33 commands: по одной для каждого active
skill, а также `/capabilities`, `/doctor`, `/reconcile` и `/agent-profiles`.
Package tool `route` доступен без slash command.

Шесть fixed agents: `manager`, `architect`, `mapper`, `worker`, `review`,
`critic`. Selectable plugin wrappers: `rules-injector`, `rtk`, `zed-bell`.
Package tools: `capabilities`, `route`, `doctor`, `agent_profiles`, `reconcile`.

## Ownership и archive

Confirmed reconcile и uninstall архивируют только exact-owned assets перед
удалением deployed copies. Modified, user-owned, unknown, unsafe и ambiguous
entries остаются без изменений как findings или conflicts. Worktrees и runtime
state сохраняются. Archive поддерживает transactional rollback и read-only
просмотр через `doctor`; команд restore или purge нет.

## Machine-readable sources

Точные имена, replacements, historical hashes и source metadata находятся в
`packages/opencode/assets/migration-inventory.json`. Active package surfaces
находятся в `packages/opencode/src/catalog.ts`, portable release metadata - в
`packages/skills/package.json`, а build-only shared-file declarations - в
`shared/manifest.json`.
