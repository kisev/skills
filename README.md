# Agent Skills

Этот репозиторий - публичный источник переносимых Agent Skills. Каждый каталог в
`skills/` является самодостаточной единицей установки и работы.

## Установка

Установите весь набор напрямую из checkout через `npx skills`:

```shell
npx skills add . --agent codex --agent opencode --copy
```

Для установки одного skill укажите его имя:

```shell
npx skills add . --skill project-spec --agent codex --copy
```

Список доступных skills выводит `npx skills add . --list`. Проверенные targets -
Codex и OpenCode; skills не требуют специфичного для target runtime и используют
только стандартные возможности host и файлы под собственным корнем.

## Набор skills

| Skill | Назначение |
| --- | --- |
| `agents-md` | Создание и проверка инструкций `AGENTS.md` по фактам репозитория. |
| `askme` | Последовательное интервью для уточнения задачи или решения. |
| `ast-grep` | Структурный поиск и подтверждённый AST rewrite через внешний CLI. |
| `commit-msg` | Одно английское Conventional Commit сообщение по локальным изменениям. |
| `doit` | Выполнение инженерной задачи с preview, проверками и отдельным commit. |
| `docs-prepare` | Подготовка одного пользовательского документа Diataxis. |
| `docs-review` | Read-only проверка пользовательской документации. |
| `humanize` | Естественный русский текст без канцелярита. |
| `project-spec` | Четыре режима работы с canonical `specs/`: init, onboard, update и audit. |
| `rtk` | Выборочное применение внешнего RTK для шумного вывода. |
| `skill-improver` | Цикл проверки и улучшения одного Agent Skill. |
| `stopit` | Обезличенная передача контекста во временный файл. |
| `summary` | Точный структурированный итог транскрипции, заметок или исследования. |
| `task-triage` | Read-only содержательный разбор конкретных GitLab-задач. |
| `task-review` | Проверка оформления и служебных полей GitLab-задач и MR. |
| `task-prepare` | Подготовка одной задачи или явного пакета задач без публикации. |
| `mr-prepare` | Подготовка обычного GitLab MR по diff, коммитам и CI. |
| `code-review` | Глубокое ревью GitLab MR или локального WIP. |
| `release-prepare` | Подготовка релизного MR, inventory и плана публикации. |
| `release-review` | Read-only проверка готовности релизного MR. |
| `mattermost` | Ограниченное read-only чтение Mattermost по ссылке. |
| `team-workflow` | Одно явное действие командного цикла по явному context. |
| `walkthrough` | Read-only карта чтения current diff, range или diff-file. |
| `attempt` | Чтение и безопасная отмена Background Attempts OpenCode. |
| `goal` | Проверяемая цель, привязанная к session OpenCode. |
| `schedule` | Явные disabled-by-default definitions для scheduler OpenCode. |
| `multi-run` | Изолированные attempts и подтверждённый fusion. |
| `usage` | Read-only ledger токенов и стоимости OpenCode. |
| `overview` | Read-only сводка durable OpenCode state. |
| `lsp-report` | Применимость LSP OpenCode без запуска и установки. |

## Границы

- `skills/` содержит переносимые самодостаточные skills, устанавливаемые через
  `npx skills`.
- Пользовательского CLI нет. Некоторые skills включают автономные Python runners
  со стандартной библиотекой Python 3.12+. Необязательная OpenCode-интеграция с
  agents, commands, runtime plugin и явным installer находится в
  `packages/opencode/` и не входит в установку skills.
- После установки skill должен работать, не читая файлы за пределами своего
  каталога. Общие исходные материалы перед выпуском детерминированно
  копируются в каждый skill-потребитель.
- Skills, которые могут записывать файлы, показывают точный предпросмотр и ждут
  явного подтверждения. Интерактивные вопросы используют штатный механизм host,
  а при его отсутствии задаются в чате.
- Skills не заменяют политики репозитория, проверку секретов, ревью или команды
  проекта. Они не создают slash-команды и не устанавливают зависимости.
- `ast-grep` и `rtk` требуют соответствующий внешний CLI. Их runners проверяют
  доступность и возвращают `escalate`, но никогда не выполняют установку.
- Семь OpenCode-specialized skills требуют OpenCode 1.18.29+ и optional package
  `agent-skills-opencode`, но по-прежнему устанавливаются отдельно через `npx skills`.
  Их Python runners используют только stdlib, работают из foreign CWD и хранят
  state только в XDG/OpenCode user-owned roots.

Репозиторий распространяется по лицензии MIT. См. [LICENSE](LICENSE).

## Проверки сопровождающего

```shell
python3 scripts/sync_shared.py
python3 scripts/sync_shared.py --check
python3 -m unittest discover -s tests -v
npx --yes skills add . --list
for skill in skills/*; do uvx --from skills-ref agentskills validate "$skill"; done
```

Команда `npx skills` - интерфейс установки. Репозиторий не добавляет другой
установщик и не содержит скрытой зависимости от конкретного host. OpenCode
assets устанавливаются отдельным opt-in installer из `packages/opencode/` после
установки skills.
