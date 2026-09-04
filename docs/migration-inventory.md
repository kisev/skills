# Инвентарь миграции

Этот каталог фиксирует переносимые skills, поставляемые этим репозиторием. Каждый
из них устанавливается отдельно через `npx skills` и не зависит от файлов checkout
после установки.

| Skill | Режим | Назначение |
| --- | --- | --- |
| `agents-md` | read/write с preview | Инструкции агентам в области репозитория. |
| `askme` | read-only | Интервью для уточнения задачи и решения. |
| `ast-grep` | read/write с digest | Структурный поиск и подтверждённый AST rewrite. |
| `commit-msg` | read-only | Сообщение commit по фактическим изменениям. |
| `doit` | write с preview | Инженерная задача в current worktree или явно выбранном worktree. |
| `docs-prepare` | write с preview | Один пользовательский документ Diataxis. |
| `docs-review` | read-only | Проверка пользовательской документации. |
| `humanize` | read-only | Естественный русский текст. |
| `project-spec` | read/write или read-only | Canonical specification в четырёх явных режимах. |
| `rtk` | read-only проверка CLI | Выборочное сжатие шумного вывода внешним CLI. |
| `skill-improver` | read-only checker | Цикл проверки одного Agent Skill. |
| `stopit` | write с preview | Обезличенная передача контекста вне репозитория. |
| `summary` | read-only по умолчанию | Структурированный итог переданных материалов. |
| `walkthrough` | read-only runner | Карта чтения current diff, Git range или diff-file. |

Skills не наследуют runtime state, providers, глобальные конфигурации или имена
инструментов конкретного host. Интерактивность выражена нейтрально: штатный
механизм host, а при его отсутствии - вопрос в чате.

Каталог `skills/` не содержит commands, agents, plugins или package. Контекстная
логика находится в `SKILL.md`; runner-ы при необходимости лежат в собственном
каталоге skill. Их общий минимальный stdlib-код хранится в `shared/references/` и
детерминированно materialize-ится в каждую зависимую установку.
