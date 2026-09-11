# Инвентарь миграции

[English](../migration-inventory.md)

## Текущий выпуск

Точный текущий portable source:
`https://github.com/kisev/skills/tree/v2.0.6`. Optional integration package:
`@kisev/skills-opencode@2.0.6`. Latest source отдельно выбирается через
`kisev/skills`.

## Активные portable skills

Активны ровно 29 portable skills:

`agents-md`, `askme`, `ast-grep`, `code-explain`, `code-review`, `commit-msg`,
`docs-prepare`, `docs-review`, `doit`, `goal`, `humanize`, `lsp-report`,
`mattermost`, `mr-prepare`, `release-prepare`, `release-review`, `rtk`,
`skill-improve`, `slides-prompts-prepare`, `spec-manage`, `stopit`, `summary`,
`task-prepare`, `task-review`, `task-triage`, `team-retro`, `team-roadmap`,
`team-sprint-close`, `team-sprint-start`.

Source, build и distribution inventories содержат те же self-contained skills.
Generated shared files объявлены в `shared/manifest.json` и проверяются
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

Операция `update` в CLI `skills` не удаляет renamed или deleted skills. Для
Codex-only cleanup эти exact names удаляются явно через pinned CLI. Для OpenCode
или shared installation их также можно удалить явно либо применить package
reconcile, только если exact ownership доказан.

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
находятся в `packages/opencode/src/catalog.ts`, declarations generated shared
copies - в `shared/manifest.json`.
