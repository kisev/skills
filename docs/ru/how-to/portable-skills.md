# Управление portable skills

[English](../../how-to/portable-skills.md)

Используйте эту инструкцию для установки, обновления, смены source, очистки или
диагностики portable skills. Эти операции не зависят от
`@kisev/skills-opencode`.

## Выберите scope и host

| Выбор           | Option                                  | Canonical location                    |
| --------------- | --------------------------------------- | ------------------------------------- |
| Global scope    | Добавьте `--global`                     | `~/.agents/skills`                    |
| Project scope   | Не передавайте `--global`               | `.agents/skills`                      |
| Только Codex    | `--agent codex`                         | Выбранный scope                       |
| Только OpenCode | `--agent opencode`                      | Выбранный scope                       |
| Оба host        | `--agent opencode --agent codex --copy` | Одна canonical copy в выбранном scope |

## Установка

Установите все skills глобально для обоих host:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --agent opencode --agent codex --skill '*' --copy --global --yes
```

Установите все skills в текущем project:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --agent opencode --agent codex --skill '*' --copy --yes
```

Чтобы установить один skill, замените `'*'` его точным именем из
[каталога skills](../reference/skill-catalog.md). Посмотреть опубликованный catalog
без записи:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --list
```

URL GitHub Pages - поддерживаемый moving stable-release channel. Его release
metadata указывает release и source revision, а Pages index связывает каждый
archive с SHA-256 digest. Текущий GitHub Release доступен по адресу
`https://github.com/kisev/skills/releases/latest`. Authored repository намеренно
не является install source.

## Обновление

Обновите отслеживаемые global skills, установленные из Pages:

```shell
npx --yes skills@latest update --global --yes
```

Для project scope не передавайте `--global`. Installation, созданная из Git
repository или tag, остаётся привязанной к этому source. Повторите подходящую
команду `add` с URL Pages, тем же scope и теми же agents, чтобы сменить source.

`update` обновляет отслеживаемые skills, но не удаляет имена, переименованные или
удалённые upstream. У OpenCode package assets отдельный update lifecycle,
описанный в [инструкции по интеграции
OpenCode](opencode-integration.md#обновление).

## Удаление retired names

Текущий [инвентарь миграции](../migration-inventory.md) определяет восемь retired
names. Для global installation, общей для OpenCode и Codex, удалите их явно:

```shell
npx --yes skills@latest remove attempt schedule usage overview project-spec skill-improver walkthrough team-workflow --agent opencode --agent codex --global --yes
```

Только для Codex используйте:

```shell
npx --yes skills@latest remove attempt schedule usage overview project-spec skill-improver walkthrough team-workflow --agent codex --global --yes
```

Используйте те же agents и scope, что при installation. Для project scope не
передавайте `--global`. Не применяйте `remove --all`, если не хотите удалить
каждый portable skill в этом scope.

Не используйте package install или reconcile для обновления или удаления
portable skills. Package reconcile управляет только package-owned assets и
сохраняет conflicts, worktrees и runtime state.

## Диагностика обнаружения

Посмотрите установленные global skills:

```shell
npx --yes skills@latest list --global
```

Для project scope не передавайте `--global`. Если новый установленный skill не
виден, проверьте `~/.agents/skills` или `.agents/skills` и перезапустите host.
После переименования skill в новом выпуске повторите `add` для additions и явно
удалите retired names.

## Границы

- Portable skills автономны и после установки не зависят от repository или
  OpenCode npm package.
- Поддерживаемая distribution - `https://kisev.github.io/skills`; source
  provenance записан в её release metadata и доступен через
  `https://github.com/kisev/skills/releases/latest`.
- Stable portable installer - `npx --yes skills@latest`.
- Updates не удаляют retired names автоматически.
- Skills не заменяют repository policy, review, secret scanning или access
  control.
