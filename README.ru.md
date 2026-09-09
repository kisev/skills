# Agent Skills

[English](README.md) | [Русский](README.ru.md)

Переносимый набор Agent Skills для инженерной работы с репозиториями,
документацией, GitLab-процессами и OpenCode. Каждый каталог в `skills/` -
самодостаточная единица установки: после установки skill не читает checkout и
не зависит от runtime конкретного host.

## Быстрый старт

Установите весь набор для OpenCode в текущий проект:

```shell
npx --yes skills@1.5.23 add kisev/skills --agent opencode --skill '*' --copy --yes
```

Это публичный direct Git contract. Для Codex замените `--agent opencode` на
`--agent codex`; для одного skill замените `'*'` его именем.

Для воспроизводимой установки актуального релиза используйте GitHub tag:

```shell
npx --yes skills add https://github.com/kisev/skills/tree/v1.2.0 \
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

## Разработка репозитория

Локальная обвязка не зависит от других checkout. Установите все закреплённые
runtimes и CLI из корня репозитория одной командой:

```shell
mise install
```

`mise.toml` фиксирует Python 3.12, Node.js 22 и standalone-инструменты.
Python-зависимости проверок находятся в `pyproject.toml` и `uv.lock`; переносимые
runners по-прежнему используют только standard library. Отдельный npm package в
`packages/opencode/` сохраняет собственные `package.json` и `package-lock.json`.
Корневого npm workspace нет.

Единый локальный и CI quality gate:

```shell
task check
```

Доступные задачи показывает `task --list`. Только `task format` изменяет
tracked-файлы. `task generate` создаёт ignored `.build/skills`, build-only
`@kisev/skills` archive/index и package staging. `task generate:check` проверяет
воспроизводимость artifacts без записи в source tree.

Установить Git hooks можно командой `lefthook install`. `pre-commit` вызывает
`task pre-commit`, который выбирает non-mutating проверки по staged paths:
Markdown/data, Python/skills и OpenCode package проверяются независимо, а
docs-only правка не запускает package lifecycle. `pre-push` вызывает полный
`task check`. Hooks не форматируют файлы и не добавляют их в index.

Если проверка не видит нужный executable, запустите `mise install`, затем
`mise current`. При ошибке `uv.lock` используйте `uv sync --locked`: изменение
lock-файла при этом считается drift. Для generated drift меняйте источник в
`shared/references/` или `packages/opencode/src/registry.ts` и запускайте
`task generate`, а не редактируйте build artifact вручную. Полная структура
проверок описана в [CONTRIBUTING.md](CONTRIBUTING.md).

## Behavioral evals

Canonical corpus находится в [`evals/`](evals/): versioned JSON Schemas,
неизменяемые scenario ID/revision и SHA-256 digest. `task eval:check` проверяет
schemas и corpus, затем запускает только offline deterministic suite. Он не
требует OpenCode, Codex, сети, credentials или пользовательской конфигурации.

Live-проверка не имеет default model и запускается только в доверенном контуре с
точными host, model и limits:

```shell
uv run --locked python scripts/eval_runner.py --trusted-live \
  --host opencode --model provider/exact-model --timeout 60 \
  --max-tokens 3000 --max-cost 2 --output evals/live/result.json
```

`evals/live/` игнорируется Git. Workflow `Trusted live evaluations` доступен
только через ручной `workflow_dispatch`, использует protected environment и не
выполняется для pull request или fork.

## Каталог skills

| Skill             | Назначение                                                                |
| ----------------- | ------------------------------------------------------------------------- |
| `agents-md`       | Создание и проверка инструкций `AGENTS.md` по фактам репозитория.         |
| `askme`           | Последовательное интервью для уточнения задачи или решения.               |
| `ast-grep`        | Структурный поиск и подтверждённый AST rewrite через внешний CLI.         |
| `commit-msg`      | Одно английское Conventional Commit сообщение по локальным изменениям.    |
| `doit`            | Выполнение инженерной задачи с preview, проверками и отдельным commit.    |
| `docs-prepare`    | Подготовка одного пользовательского документа Diataxis.                   |
| `docs-review`     | Read-only проверка пользовательской документации.                         |
| `humanize`        | Естественный русский текст без канцелярита.                               |
| `project-spec`    | Четыре режима работы с canonical `specs/`: init, onboard, update и audit. |
| `rtk`             | Выборочное применение внешнего RTK для шумного вывода.                    |
| `skill-improver`  | Цикл проверки и улучшения одного Agent Skill.                             |
| `stopit`          | Обезличенная передача контекста во временный файл.                        |
| `summary`         | Точный структурированный итог транскрипции, заметок или исследования.     |
| `task-triage`     | Read-only содержательный разбор конкретных GitLab-задач.                  |
| `task-review`     | Проверка оформления и служебных полей GitLab-задач и MR.                  |
| `task-prepare`    | Подготовка одной задачи или явного пакета задач без публикации.           |
| `mr-prepare`      | Подготовка обычного GitLab MR по diff, коммитам и CI.                     |
| `code-review`     | Глубокое ревью GitLab MR или локального WIP.                              |
| `release-prepare` | Подготовка релизного MR, inventory и плана публикации.                    |
| `release-review`  | Read-only проверка готовности релизного MR.                               |
| `mattermost`      | Строго ограниченное чтение Mattermost с кэшем по identity.                |
| `team-workflow`   | Одно явное действие командного цикла по явному context.                   |
| `walkthrough`     | Read-only карта чтения current diff, range или diff-file.                 |
| `attempt`         | Чтение и безопасная отмена Background Attempts OpenCode.                  |
| `goal`            | Read-only формулировка проверяемой цели в `work-item/v1`.                 |
| `schedule`        | Явные disabled-by-default definitions для scheduler OpenCode.             |
| `usage`           | Read-only ledger токенов и стоимости OpenCode.                            |
| `overview`        | Read-only сводка durable OpenCode state.                                  |
| `lsp-report`      | Применимость LSP OpenCode без запуска и установки.                        |

`askme`, `task-prepare`, `task-review` и `goal` используют общий materialized
контракт `work-item/v1`. Он не создаёт зависимость установленного skill от
`shared/`; validator и schema входят в каждую portable-копию.

## Build Distribution

`skills/<name>/` уже содержит committed generated copies и устанавливается без
сборки. `task generate` проверяет/materialize-ит эти copies, затем создаёт
ignored `.build/skills` и private build-only package `@kisev/skills`: well-known index,
`skills-lock.json` с SHA-256 и отдельный self-contained `.tar.gz` для каждого
skill. В каждом archive `SKILL.md` находится в корне. Index фиксирует source
revision; будущая публикация будет доступна по
`https://unpkg.com/@kisev/skills@<version>/`. Текущий released source остаётся
tag `v1.2.0`; build не создаёт tag, npm release или GitHub Release.

Подробная классификация режимов и границ записана в
[migration inventory](docs/migration-inventory.md).

## OpenCode integration

Portable skills и OpenCode integration устанавливаются независимо. Сначала
установите skills, затем в каталоге, из которого OpenCode разрешает npm packages,
установите integration:

```shell
npm install @kisev/skills-opencode@1.2.0
npm exec -- skills-opencode install --scope global --dry-run
```

Dry-run выводит короткий план по группам, только изменяемые paths, conflicts,
restart flag, SHA-256 digest и готовую confirm-команду. Применяйте только digest
из этого вывода:

```shell
npm exec -- skills-opencode install --scope global --confirm <digest>
```

Для scripts и полного machine-readable плана добавьте `--json`.

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

Управление моделями fixed agents и additional critics выполняется напрямую через
CLI без LLM-токенов. Например:

```shell
npm exec -- skills-opencode agent list --scope global
npm exec -- skills-opencode agent configure manager --scope global --dry-run
npm exec -- skills-opencode critic add security --scope global \
  --model anthropic/claude-sonnet-4-6 --dry-run
```

Каждая mutation сначала создаёт короткий plan и private одноразовый receipt с
TTL. Применить plan можно только командой с `--confirm <digest>`. Команды
`/agent-list`, `/agent-model-set`, `/critic-add` и `/critic-remove` и package tool
`agent_profiles` остаются опциональными thin adapters; рекомендуемый интерфейс -
прямой CLI.

## Совместимость и требования

- Portable skills устанавливаются через pinned `npx --yes skills@1.5.23`; целевые hosts
  должны поддерживать Agent Skills.
- Раннеры, которые входят в отдельные skills, используют только Python 3.12+
  standard library. Большинству skills Python не нужен.
- `ast-grep` и `rtk` требуют заранее установленный одноимённый CLI; skills не
  выполняют их установку.
- `@kisev/skills-opencode` targets OpenCode `>=1.18.29 <1.19.0`.
  npm package требует Node.js 22+.
- OpenCode assets являются опциональными: portable skills продолжают работать без
  npm package, commands, agents и plugins.

GitLab skills используют один canonical private collection по identity GitLab
object, а не по имени вызывающего skill. Установленные copies содержат byte-identical
runtime, artifact schema и workflow contract. Collection ограничен GET-only
allowlist, exact SHA и completeness; publication остается только локальным
Markdown-планом с `external_mutations=false`.

## Ограничения runtime

Следующие ограничения делают stateful
OpenCode plugins небезопасными для включения:

- Background Attempts владеют managed worktree и terminal reconciliation;
  plugin остаётся opt-in.
- Cron scheduler использует строгий evaluator и machine-readable receipts;
  definitions и plugin остаются disabled-by-default.
- Mattermost имеет неполный parity с заявленными сценариями.
- Runtime state и `doctor` требуют дополнительного hardening.

Wrappers `background-attempts`, `schedule` и `autonomy-policy` выключены по
умолчанию. `goal` не является wrapper-ом и не создаёт state. OpenChamber Goal
Mode как внешний способ выполнения цели не меняется; lifecycle этого проекта и
auto-continuation удалены.

## Обновление и удаление

Обновите установленные skills стандартной командой `skills`:

```shell
npx --yes skills update --yes
```

Для OpenCode integration установите требуемую версию, затем повторите dry-run и
подтвердите новый digest:

```shell
npm install @kisev/skills-opencode@1.2.0
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
python3 scripts/build_skills.py --check
python3 scripts/build_skills.py --generate
python3 -m unittest discover -s tests -v
for skill in skills/*; do uvx --from skills-ref agentskills validate "$skill"; done
npx --yes skills add . --list
```

Репозиторий распространяется по лицензии MIT. См. [LICENSE](LICENSE).
