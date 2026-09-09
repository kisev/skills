# Инвентарь миграции

[English](../migration-inventory.md) | [Русский](migration-inventory.md)

Этот каталог фиксирует переносимые skills, поставляемые этим репозиторием. Каждый
из них устанавливается отдельно через `npx skills` и не зависит от файлов checkout
после установки.

| Skill             | Режим                                 | Назначение                                                                                       |
| ----------------- | ------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `agents-md`       | read/write с preview                  | Инструкции агентам в области репозитория.                                                        |
| `askme`           | read-only                             | Интервью для уточнения задачи и решения.                                                         |
| `ast-grep`        | read/write с digest                   | Структурный поиск и подтверждённый AST rewrite.                                                  |
| `commit-msg`      | read-only                             | Сообщение commit по фактическим изменениям.                                                      |
| `doit`            | write с preview                       | Инженерная задача в current worktree или явно выбранном worktree.                                |
| `docs-prepare`    | write с preview                       | Один пользовательский документ Diataxis.                                                         |
| `docs-review`     | read-only                             | Проверка пользовательской документации.                                                          |
| `humanize`        | read-only                             | Естественный русский текст.                                                                      |
| `project-spec`    | read/write или read-only              | Canonical specification в четырёх явных режимах.                                                 |
| `rtk`             | read-only проверка CLI                | Выборочное сжатие шумного вывода внешним CLI.                                                    |
| `skill-improver`  | read-only checker                     | Цикл проверки одного Agent Skill.                                                                |
| `stopit`          | write с preview                       | Обезличенная передача контекста вне репозитория.                                                 |
| `summary`         | read-only по умолчанию                | Структурированный итог переданных материалов.                                                    |
| `task-triage`     | read-only                             | Содержательный разбор конкретных GitLab-задач.                                                   |
| `task-review`     | read-only                             | Проверка оформления и служебных полей GitLab-задач и MR.                                         |
| `task-prepare`    | local plan                            | Подготовка одной или пакета GitLab-задач без публикации.                                         |
| `mr-prepare`      | local plan                            | Подготовка обычного GitLab MR по diff, коммитам и CI.                                            |
| `code-review`     | read-only и local plan                | Глубокое ревью GitLab MR или local WIP.                                                          |
| `release-prepare` | local plan                            | Подготовка release MR, inventory и плана публикации.                                             |
| `release-review`  | read-only                             | Проверка готовности release MR.                                                                  |
| `mattermost`      | read-only с private кэшем по identity | Строго ограниченное чтение Mattermost, треда и состава канала.                                   |
| `team-workflow`   | read/write с confirmation             | Одно явное действие командного цикла по explicit context.                                        |
| `walkthrough`     | read-only runner                      | Карта чтения current diff, Git range или diff-file.                                              |
| `attempt`         | package tool                          | Чтение и подтверждённая отмена bounded Background Attempts.                                      |
| `goal`            | read-only portable skill              | Формулировка проверяемой цели в canonical `work-item/v1`.                                        |
| `schedule`        | write с confirmation                  | Явные definitions, disabled по умолчанию, без replay пропущенных slots.                          |
| `usage`           | read-only runner                      | Ledger observed tokens/cost с честным unknown.                                                   |
| `overview`        | read-only runner                      | Partial-tolerant сводка file-backed OpenCode state.                                              |
| `lsp-report`      | read-only runner                      | Применимые LSP без запуска servers и установки tools; использует canonical materialized catalog. |

Skills не наследуют runtime state, providers, глобальные конфигурации или имена
инструментов конкретного host. Интерактивность выражена нейтрально: штатный
механизм host, а при его отсутствии - вопрос в чате.

Четыре workflow `askme`, `task-prepare`, `task-review` и `goal` используют общий
versioned `work-item/v1`: problem/outcome, criteria/evidence, scope/non-goals,
dependencies/actions/assumptions, safety, risks/questions и stop conditions.
Machine validator проверяет форму, ссылки, границы, DAG и стабильность report;
feasibility и смысловые противоречия приходят отдельным structured semantic
assessment. `goal` не создаёт state и не запускает lifecycle. Optional premortem
выполняется один раз независимым агентом либо возвращает `skipped` без блокировки.

Каталог `skills/` не содержит commands, agents или plugins. Контекстная логика
находится в `SKILL.md`; runner-ы при необходимости лежат в собственном каталоге
skill. Их общий минимальный stdlib-код хранится в `shared/references/` и
детерминированно materialize-ится и committed в каждый зависимый source-каталог
`skills/<name>/`, поэтому clean Git clone устанавливается напрямую. Необязательный
package `packages/opencode/` содержит OpenCode-specific assets, runtime и opt-in
installer, но не поставляет копии skills и не меняет их установку через
`npx skills`. Agent profiles управляются package domain и прямым CLI, а не
отдельным skill; четыре slash-команды и tool `agent_profiles` только адаптируют
этот интерфейс. Stateful plugins выключены по умолчанию.

Machine-readable история public surfaces находится в
`packages/opencode/assets/migration-inventory.json`. Она содержит только
переносимые skills, package assets и installation metadata, доступные через
public GitHub tags или npm releases. Retired entries удаляются только после
проверки exact SHA-256 и scope-bound confirmation.
