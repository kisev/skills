# Agent Skills

Переносимый набор Agent Skills для инженерной работы с репозиториями,
документацией, GitLab-процессами и OpenCode. Каждый каталог в `skills/` -
самодостаточная единица установки: после установки skill не читает checkout и
не зависит от runtime конкретного host.

## Быстрый старт

Установите весь набор для OpenCode в текущий проект:

```shell
npx --yes skills add kisev/skills --agent opencode --skill '*' --copy --yes
```

Для воспроизводимой установки первого публичного релиза используйте GitHub tag:

```shell
npx --yes skills add https://github.com/kisev/skills/tree/v1.0.0 \
  --agent opencode --skill '*' --copy --yes
```

Для одного skill замените `--skill '*'` его именем:

```shell
npx --yes skills add kisev/skills --agent opencode \
  --skill project-spec --copy --yes
```

`npx skills` по умолчанию устанавливает в project scope. Добавьте `--global`,
если skills должны быть доступны всем проектам пользователя. Перед установкой
можно просмотреть каталог без записи:

```shell
npx --yes skills add kisev/skills --list
```

## Каталог skills

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

Подробная классификация режимов и границ записана в
[migration inventory](docs/migration-inventory.md).

## OpenCode integration

Portable skills и OpenCode integration устанавливаются независимо. Сначала
установите skills, затем в каталоге, из которого OpenCode разрешает npm packages,
установите integration:

```shell
npm install @kisev/skills-opencode@1.0.0
npm exec -- skills-opencode install --scope global --dry-run
```

Dry-run выводит точный план и SHA-256 digest. Применяйте только digest из этого
вывода:

```shell
npm exec -- skills-opencode install --scope global --confirm <digest>
```

`global` размещает управляемые assets в OpenCode user config. Для текущего
репозитория используйте `--scope project`; installer добавляет только файлы под
`.opencode/`. Он не создаёт и не редактирует `opencode.json`.

Подключите plugin вручную в `opencode.json` или `opencode.jsonc`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@kisev/skills-opencode"]
}
```

После установки, обновления или удаления integration полностью перезапустите
OpenCode: agents и commands обнаруживаются до plugin hooks. Полное описание
installer, plugin factories и ownership-границ есть в
[README package](packages/opencode/README.md).

## Совместимость и требования

- Portable skills устанавливаются через актуальный `npx skills`; целевые hosts
  должны поддерживать Agent Skills.
- Раннеры, которые входят в отдельные skills, используют только Python 3.12+
  standard library. Большинству skills Python не нужен.
- `ast-grep` и `rtk` требуют заранее установленный одноимённый CLI; skills не
  выполняют их установку.
- OpenCode-specific skills и `@kisev/skills-opencode` требуют OpenCode 1.18.29+.
  npm package требует Node.js 22+.
- OpenCode assets являются опциональными: portable skills продолжают работать без
  npm package, commands, agents и plugins.

## Обновление и удаление

Обновите установленные skills стандартной командой `skills`:

```shell
npx --yes skills update --yes
```

Для OpenCode integration установите требуемую версию, затем повторите dry-run и
подтвердите новый digest:

```shell
npm install @kisev/skills-opencode@1.0.0
npm exec -- skills-opencode install --scope global --dry-run
npm exec -- skills-opencode install --scope global --confirm <digest>
```

Удаление одного portable skill выполняется явно по имени:

```shell
npx --yes skills remove project-spec --agent opencode --yes
```

Удаление OpenCode assets также начинается с dry-run:

```shell
npm exec -- skills-opencode uninstall --scope global --dry-run
npm exec -- skills-opencode uninstall --scope global --confirm <digest>
```

Uninstaller удаляет только неизменённые managed files. Пользовательские изменения
сохраняются как конфликт и требуют ручного решения.

## Безопасность и ограничения

- Skills с записью сначала показывают preview и требуют явное подтверждение.
- Installer не имеет lifecycle hooks, не выполняет автоматическую установку skills
  и не изменяет пользовательскую конфигурацию OpenCode. Он не перезаписывает
  неизвестные или изменённые файлы.
- Stateful OpenCode plugins и Zed integrations выключены по умолчанию. Включайте
  их только в своём user-owned plugin wrapper.
- Skills не заменяют review, policies, проверку секретов и контроль доступа
  проекта. Внешние CLI и сервисы остаются отдельными пользовательскими границами.
- Некоторые skills требуют уже настроенную авторизацию внешнего инструмента. Не
  передавайте пароли, MFA-коды или tokens в prompt, argv или логи.
- `npx skills remove --all` затрагивает все skills в выбранном scope; для этого
  набора безопаснее удалять skills по одному имени.

Сведения о сообщении уязвимостей приведены в [SECURITY.md](SECURITY.md), а правила
внесения изменений - в [CONTRIBUTING.md](CONTRIBUTING.md). История выпусков - в
[CHANGELOG.md](CHANGELOG.md).

## Для сопровождающих

```shell
python3 scripts/sync_shared.py --check
python3 -m unittest discover -s tests -v
for skill in skills/*; do uvx --from skills-ref agentskills validate "$skill"; done
npx --yes skills add . --list
```

Репозиторий распространяется по лицензии MIT. См. [LICENSE](LICENSE).
