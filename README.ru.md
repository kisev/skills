# Agent Skills

[English](README.md) | [Русский](README.ru.md)

Переносимые Agent Skills для Codex и OpenCode с дополнительной npm-интеграцией
для OpenCode.

## Два независимых слоя

| Слой                          | Global location                             | Project location                                       |
| ----------------------------- | ------------------------------------------- | ------------------------------------------------------ |
| Portable skills               | `~/.agents/skills`                          | `.agents/skills`                                       |
| Optional OpenCode integration | npm project и assets в `~/.config/opencode` | package в project `node_modules`, assets в `.opencode` |

У этих слоёв независимые lifecycle установки, обновления и удаления. Portable
skills содержат workflows и работают без npm package. Package добавляет OpenCode
commands, agents, tools, routing и optional plugin wrappers, но не содержит и не
устанавливает portable skills.

## Быстрый global-старт

Установите текущую стабильную portable distribution `v2.2.0` для обоих host:

```shell
npx --yes skills@1.5.23 add https://kisev.github.io/skills --agent opencode --agent codex --skill '*' --copy --global --yes
```

Команда создаёт одну canonical copy в `~/.agents/skills` для обоих host.

## Codex и OpenCode

- Только Codex: используйте `--agent codex`.
- Только OpenCode: используйте `--agent opencode`.
- Оба host: используйте `--agent opencode --agent codex`; `--copy` сохраняет одну
  canonical copy в выбранном scope.

Для project installation не передавайте `--global`. Canonical project copy
находится в `.agents/skills`:

```shell
npx --yes skills@1.5.23 add https://kisev.github.io/skills --agent opencode --agent codex --skill '*' --copy --yes
```

Для OpenCode используйте обязательный flow: установите package постоянно в
принадлежащем ему npm project, запустите `skills-opencode install --dry-run`,
выполните exact confirmation command, добавьте package в user-owned `plugin` и
перезапустите OpenCode. Перед каждым reconcile обязательно установите или
обновите package. Только после этого запускайте reconcile. Package должен
оставаться установленным в project `node_modules` или в npm project
`~/.config/opencode`; следуйте [инструкции по интеграции OpenCode](packages/opencode/README.ru.md).
Installer не устанавливает portable skills и не меняет `opencode.json`.

Installer сохраняет четыре независимые группы wizard: Skill command adapters,
Package command adapters, Fixed agents и Selectable plugins. Выбор adapter
выбирает package command assets, а не portable skills. Portable skills
устанавливаются только pinned командой `npx --yes skills@1.5.23` выше.

## Опубликованная distribution и provenance исходников

Поддерживаемый portable source - стабильный канал GitHub Pages по адресу
`https://kisev.github.io/skills`. В этом выпуске его metadata указывает версию
`2.2.0` и commit с tag `v2.2.0`. Посмотреть catalog без записи:

```shell
npx --yes skills@1.5.23 add https://kisev.github.io/skills --list
```

URL Pages является moving stable-release channel, а не immutable URL tag. Git
tags задают provenance исходников, а Pages index связывает каждый автономный
archive с SHA-256 digest. Для установки одного skill замените `'*'` его точным
текущим именем. Authored repository намеренно не является install source.

## Обновление

Installation из Pages следует за последующими stable archive digests:

```shell
npx --yes skills@1.5.23 update --global --yes
```

Для project scope не передавайте `--global`. Installation, ранее созданная из Git
repository или tag, остаётся привязанной к этому source; повторите `add` с URL
Pages, тем же scope и agents, чтобы перепривязать её. `update` обновляет
отслеживаемые skills, но не удаляет имена, переименованные или удалённые upstream.

OpenCode integration обновляется независимо: установите точную npm version в
принадлежащем ей npm project, запустите новый `install --dry-run`, выполните
точную confirmation command из preview и перезапустите OpenCode. См.
[порядок обновления package](packages/opencode/README.ru.md#обновление).

## Очистка

Текущий migration inventory содержит ровно восемь retired portable names:

| Retired                                    | Replacement                                                                                      |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| `attempt`, `schedule`, `usage`, `overview` | Нет                                                                                              |
| `project-spec`                             | `spec-manage`                                                                                    |
| `skill-improver`                           | `skill-improve`                                                                                  |
| `walkthrough`                              | `code-explain`                                                                                   |
| `team-workflow`                            | `team-sprint-start`, `team-sprint-close`, `team-retro`, `team-roadmap`, `slides-prompts-prepare` |

Для Codex-only global installation удалите имена явно:

```shell
npx --yes skills@1.5.23 remove attempt schedule usage overview project-spec skill-improver walkthrough team-workflow --agent codex --global --yes
```

Для OpenCode installation или общей для обоих host canonical copy либо удалите
имена явно для выбранных agents:

```shell
npx --yes skills@1.5.23 remove attempt schedule usage overview project-spec skill-improver walkthrough team-workflow --agent opencode --agent codex --global --yes
```

Не используйте package install или reconcile для обновления или удаления
portable skills. Для project scope не передавайте `--global`. Не применяйте
`remove --all`, если не хотите удалить каждый portable skill в этом scope.
Package reconcile имеет отдельный lifecycle для package-owned assets; conflicts,
worktrees и runtime state сохраняются. Команд restore или purge для archive нет.

## Диагностика

Посмотреть установленные portable skills:

```shell
npx --yes skills@1.5.23 list --global
```

Если новый skill не виден, проверьте `~/.agents/skills` или `.agents/skills` и
перезапустите host. После смены tag повторите `add` для renamed additions и
выполните явную очистку retired names, описанную выше.

Запускайте integration doctor через npm project, где установлен package:

```shell
npm --prefix "$HOME/.config/opencode" exec -- skills-opencode doctor --scope global
npm --prefix "$HOME/.config/opencode" exec -- skills-opencode doctor --scope global --json
```

`doctor` работает без записи. Exit status `0` означает чистое состояние, `1` -
findings, `2` - invalid input или incomplete probe failure. Разбирайте conflicts,
а не перезаписывайте их.

## Профили команд

Командные skills автоматически находят приватный default profile в
`${XDG_CONFIG_HOME:-~/.config}/opencode/team-contexts/`. При первом запуске они
могут собрать его из ответов пользователя и явно указанных файлов, URL,
репозиториев или connector evidence, спросить только недостающие поля и
сохранить после confirmation-bound preview. Просьба запомнить участника, проект,
источник или визуальное предпочтение обновляет приватный profile, а не публичный
skill.

Версионированная публичная schema и обезличенный пример поставляются в каждом
командном skill как `references/team-context.schema.json` и
`references/team-context.example.json`. Profiles остаются вне этого репозитория;
не храните в них credentials или персональные заметки.

## Текущий каталог

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
| `summary`                | Превратить transcripts, notes или research в structured factual summary.                                |
| `task-prepare`           | Подготовить storage-neutral self-contained work item без публикации.                                    |
| `task-review`            | Проверить storage-neutral work item без изменения external state.                                       |
| `task-triage`            | Разобрать explicit storage-neutral work-item material без записи.                                       |
| `team-retro`             | Подготовить evidence-based retrospective или delivery presentation по приватному profile.               |
| `team-roadmap`           | Проверить или обновить evidence-based roadmap по приватному profile.                                    |
| `team-sprint-close`      | Завершить один sprint cycle по приватному profile или explicit context.                                 |
| `team-sprint-start`      | Начать один sprint cycle по приватному profile или explicit context.                                    |

Точный active и retired inventory находится в
[инвентаре миграции](docs/ru/migration-inventory.md).

## Разработка

Установите закреплённый toolchain и запустите полный quality gate:

```shell
mise install
task check
```

Полезные отдельные команды:

```shell
task eval:check
task generate:check
lefthook install
```

`task generate` создаёт ignored build outputs, не изменяя authored skills.
Portable entrypoints называются `SKILL.source.md`; build создаёт `SKILL.md` и
добавляет canonical files из `shared/references/` только в `.build/skills`. Структура checks
описана в [CONTRIBUTING.ru.md](CONTRIBUTING.ru.md).

## Справочник и ограничения

- Stable portable distribution: `https://kisev.github.io/skills` (`2.2.0`).
- Source provenance: `https://github.com/kisev/skills/tree/v2.2.0`.
- Portable installer: `npx --yes skills@1.5.23`.
- OpenCode integration: `@kisev/skills-opencode@2.2.0`, Node.js 22+, OpenCode
  `>=1.18.29 <1.19.0`.
- Portable runners используют Python 3.12+ standard library, только когда нужен
  runner.
- `ast-grep` и `rtk` требуют external CLI; skills не устанавливают эти tools.
- Skills и integration assets не заменяют repository policy, review, secret
  scanning и access control.

Behavioral coverage описано в [документе проверки](docs/ru/verification.md).
Порядок сообщения об уязвимостях находится в [SECURITY.md](SECURITY.md), история
выпусков - в [CHANGELOG.md](CHANGELOG.md), лицензия - в [LICENSE](LICENSE).
