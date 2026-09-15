# Каталог skills

[English](../../reference/skill-catalog.md)

Текущий stable release публикует 29 portable Agent Skills. Distribution
идентифицируют release metadata и archive digests; отдельные skills не содержат
version. Их workflows автономны и могут быть установлены независимо от
`@kisev/skills-opencode`.

## Active skills

| Skill                    | Назначение                                                                                              |
| ------------------------ | ------------------------------------------------------------------------------------------------------- |
| `agents-md`              | Создать или проверить repository-scoped инструкции `AGENTS.md`.                                         |
| `askme`                  | Уточнить неполную задачу или design через ограниченное интервью.                                        |
| `ast-grep`               | Выполнить structural search или confirmed AST rewrite через ast-grep.                                   |
| `code-explain`           | Построить read-only карту current WIP, Git range, branch или истории MR.                                |
| `code-review`            | Проверить GitLab MR или local WIP на дефекты и риски.                                                   |
| `commit-msg`             | Подготовить одно короткое английское commit message по local changes.                                   |
| `docs-prepare`           | Подготовить пользовательский документ по evidence и private preview.                                    |
| `docs-review`            | Проверить пользовательскую документацию на точность и удобство.                                         |
| `doit`                   | Выполнить инженерную задачу с preview, bounded writes и checks.                                         |
| `goal`                   | Подготовить read-only structured Markdown goal не длиннее 4000 символов.                                |
| `humanize`               | Сделать технический текст прямым и естественным.                                                        |
| `lsp-report`             | Показать host-neutral состояния applicability, configuration, binary и runtime LSP без запуска servers. |
| `mattermost`             | Прочитать и разобрать ограниченный Mattermost post, thread, channel или chat.                           |
| `mr-prepare`             | Подготовить metadata и local publication plan для GitLab MR.                                            |
| `release-prepare`        | Подготовить release MR, inventory, announcement и publication plan.                                     |
| `release-review`         | Проверить release MR на полноту и совместимость.                                                        |
| `rtk`                    | Выборочно использовать RTK для сжатия многословного command output.                                     |
| `skill-improve`          | Проверить и улучшить один Agent Skill в iterative loop.                                                 |
| `slides-prompts-prepare` | Соединить выбранную тему презентации с фактическими отсылками к команде и технологиям.                  |
| `spec-manage`            | Инициализировать, изучить, обновить или проверить canonical project specs.                              |
| `stopit`                 | Записать обезличенный handoff для следующей session.                                                    |
| `briefing`               | Превратить transcripts, notes или research в structured factual summary.                                |
| `task-prepare`           | Подготовить storage-neutral self-contained work item без публикации.                                    |
| `task-review`            | Проверить storage-neutral work item без изменения external state.                                       |
| `task-triage`            | Разобрать explicit storage-neutral work-item material без записи.                                       |
| `team-retro`             | Подготовить evidence-based retrospective или delivery presentation по приватному profile.               |
| `team-roadmap`           | Проверить или обновить evidence-based roadmap по приватному profile.                                    |
| `team-sprint-close`      | Завершить один sprint cycle по приватному profile или explicit context.                                 |
| `team-sprint-start`      | Начать один sprint cycle по приватному profile или explicit context.                                    |

Точные active и retired names записаны в
[инвентаре миграции](../migration-inventory.md).

## Командные profiles

Командные skills находят default private profile в
`${XDG_CONFIG_HOME:-~/.config}/opencode/team-contexts/`. При первом запуске они
могут собрать его из ответов пользователя и явно указанных файлов, URL,
репозиториев или connector evidence, спросить только недостающие поля и сохранить
после confirmation-bound preview. Просьба запомнить участника, проект, источник
или visual preference обновляет private profile, а не public skill.

Версионированная public schema и обезличенный пример поставляются в каждом
командном skill как `references/team-context.schema.json` и
`references/team-context.example.json`. Profiles остаются вне этого repository;
не храните в них credentials или персональные заметки.

## Требования и ограничения

- Portable runners используют Python 3.12+ standard library, только когда нужен
  runner.
- `ast-grep` и `rtk` требуют external CLI; skills не устанавливают их.
- Portable skills работают без `@kisev/skills-opencode`.
- Skills не заменяют repository policy, review, secret scanning, access control
  или итоговое решение пользователя.
