# Инвентарь миграции

[English](../migration-inventory.md)

## Текущий выпуск

Текущий источник переносимых навыков - стабильный канал GitHub Pages:
`https://kisev.github.io/skills`. Его метаданные указывают выпуск и ревизию
исходников, а `https://github.com/kisev/skills/releases/latest` открывает текущий
GitHub Release. Необязательный пакет интеграции - `@kisev/skills-opencode`.

## Активные переносимые навыки

Активны ровно 27 переносимых навыков:

`agents-md`, `askme`, `ast-grep`, `code-explain`, `code-review`, `commit-msg`,
`docs-prepare`, `docs-review`, `goal`, `humanize`, `mattermost`, `mr-prepare`,
`release-prepare`, `release-review`, `rtk`,
`skill-improve`, `slides-prompts-prepare`, `spec-manage`, `stopit`, `briefing`,
`task-prepare`, `task-review`, `task-triage`, `team-retro`, `team-roadmap`,
`team-sprint-close` и `team-sprint-start`.

Исходный перечень не содержит дубликатов; перечни сборки и дистрибутива содержат
те же 27 автономных навыков. Общие файлы объявлены в `shared/manifest.json`,
добавляются только в `.build/skills` и проверяются побайтово.

## Сведения об очистке переносимых навыков

Текущий инвентарь миграции содержит ровно эти одиннадцать устаревших имён переносимых
навыков. Имени `multi-run` в нём нет.

| Устаревшее имя   | Текущая замена                                                                                   |
| ---------------- | ------------------------------------------------------------------------------------------------ |
| `attempt`        | Нет                                                                                              |
| `schedule`       | Нет                                                                                              |
| `usage`          | Нет                                                                                              |
| `overview`       | Нет                                                                                              |
| `doit`           | Нет                                                                                              |
| `lsp-report`     | Нет                                                                                              |
| `project-spec`   | `spec-manage`                                                                                    |
| `skill-improver` | `skill-improve`                                                                                  |
| `walkthrough`    | `code-explain`                                                                                   |
| `team-workflow`  | `team-sprint-start`, `team-sprint-close`, `team-retro`, `team-roadmap`, `slides-prompts-prepare` |
| `summary`        | `briefing`                                                                                       |

Операция `update` в CLI `skills` обнаруживает удалённые в источнике имена и
предлагает удалить их локальные копии. Эти точные имена также можно удалить явно
через стабильный `skills@latest` с теми же агентами и областью, что и при
установке. Пакет OpenCode не проверяет и не удаляет переносимые навыки.

## Текущий состав интеграции OpenCode

Текущий состав пакета содержит 27 команд: по одной для каждого активного навыка.
Инструмент пакета `route` доступен без слеш-команды.

Шесть агентов с фиксированными ролями: `manager`, `architect`, `mapper`, `worker`,
`review`, `critic`. Доступные обёртки плагинов: `rules-injector`, `rtk`,
`zed-bell`. Единственный инструмент пакета - `route`; для администрирования
используется прямой CLI.

## Принадлежность и архив

После подтверждения `reconcile` и `uninstall` архивируют только компоненты с
точно подтверждённой принадлежностью, прежде чем удалить развёрнутые копии.
Переносимые навыки и lock-файлы их установщика не входят в область владения
пакета. Пользовательские, неизвестные, небезопасные и неоднозначные элементы
остаются без изменений и отображаются как `findings` или `conflicts`. Рабочие
деревья и runtime state сохраняются. Архив поддерживает транзакционный откат и
доступен через `doctor`; команд `restore` и `purge` нет.

## Машиночитаемые источники

Точные имена, замены, прежние контрольные суммы и метаданные источников находятся
в `packages/opencode/assets/migration-inventory.json`. Активный состав пакета
описан в `packages/opencode/src/catalog.ts`, метаданные выпуска переносимых
навыков - в `packages/skills/package.json`, а объявления общих файлов только для
сборки - в `shared/manifest.json`.
