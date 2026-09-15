# Agent Skills

[English](README.md)

Переносимые Agent Skills для Codex и OpenCode вместе с `skills-opencode` -
полноценной интеграцией для OpenCode. Эти два компонента независимы: можно
использовать любой из них отдельно или установить оба для полной работы с
OpenCode.

## Компоненты проекта

| Компонент                | Что предоставляет                                                                      | Lifecycle                                                                                           |
| ------------------------ | -------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Portable Agent Skills    | 29 автономных workflows для разработки, документации, delivery и командной работы      | Устанавливаются стабильным CLI `skills@latest` в `~/.agents/skills` или `.agents/skills`            |
| `@kisev/skills-opencode` | OpenCode commands, fixed agents, routing tools, диагностика и optional plugin wrappers | Устанавливается как npm dependency; managed assets находятся в `~/.config/opencode` или `.opencode` |

Portable skills не требуют npm package. npm package не содержит, не
устанавливает, не обновляет и не удаляет portable skills.

## Portable skills

Установите текущую стабильную portable distribution глобально для Codex и
OpenCode:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --agent opencode --agent codex --skill '*' --copy --global --yes
```

Stable channel публикует текущую release metadata и digest-bound archives.
Начните с [пошаговой установки](docs/ru/tutorials/getting-started.md), используйте
[how-to по portable skills](docs/ru/how-to/portable-skills.md) для project
installation, обновления, очистки и диагностики или откройте
[каталог skills](docs/ru/reference/skill-catalog.md).

## skills-opencode

`@kisev/skills-opencode` добавляет в OpenCode:

- slash-command adapters для установленных skills и package tools;
- шесть fixed agent roles и управление profiles;
- capability routing, установку, reconcile и doctor tooling;
- opt-in plugin wrappers `rules-injector`, `rtk` и `zed-bell`.

Установите package постоянно в npm project, которому принадлежит integration,
затем покажите preview managed assets:

```shell
npm install --save-exact @kisev/skills-opencode
npx --yes @kisev/skills-opencode@latest install --scope project --dry-run
```

Это только начало обязательного flow. Выполните exact confirmation command из
preview, добавьте package в user-owned entry `plugin` OpenCode и перезапустите
OpenCode. Следуйте полной
[инструкции по интеграции OpenCode](docs/ru/how-to/opencode-integration.md).

## Документация

[Индекс документации](docs/ru/README.md) организует tutorials, how-to guides,
reference и explanations по Diataxis. Там находятся ссылки на архитектуру,
проверку, миграцию, совместимость и оба installation lifecycle.

## Разработка

```shell
mise install
task check
```

Границы исходников и отдельные checks описаны в
[CONTRIBUTING.ru.md](CONTRIBUTING.ru.md). Порядок сообщения об уязвимостях
находится в [SECURITY.md](SECURITY.md), история выпусков - в
[CHANGELOG.md](CHANGELOG.md), лицензия - в [LICENSE](LICENSE).
