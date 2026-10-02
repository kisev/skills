# Agent Skills

[English](README.md)

Переносимые навыки для Codex и OpenCode и независимая интеграция `agentomatic` для OpenCode. Используйте любой компонент отдельно или оба вместе.

## Компоненты проекта

| Компонент | Назначение | Жизненный цикл |
| - | - | - |
| Portable Agent Skills | 38 автономных сценариев для разработки, документации, выпуска и командной работы | Стабильный CLI `skills@latest` устанавливает их в `~/.agents/skills` или `.agents/skills` |
| `@kisev/agentomatic` | Команды OpenCode, агенты с фиксированными ролями, средства маршрутизации, диагностика и необязательные обёртки плагинов | Устанавливается как зависимость npm; управляемые файлы находятся в `~/.config/opencode` или `.opencode` |

CLI `skills` управляет переносимыми навыками; npm-интеграция не содержит, не устанавливает, не обновляет, не проверяет и не удаляет их.

## Установка всего

Установите переносимые навыки, `agentomatic`, [memomatic](docs/ru/how-to/memomatic.md), [reviewmatic](apps/reviewmatic/README.ru.md) и [taskmatic](docs/ru/how-to/taskmatic.md); обновление - те же команды.
`install` и `config` требуют подтверждения в терминале или явного выбора компонентов с `--yes`. До первого стабильного релиза пакета `latest` может быть пререлизом.
После обновления перезапустите OpenCode, остальные работающие MCP-хосты и веб-сервис taskmatic.

Всё на канале `latest`:

```shell
# Registry versions
npm view --prefer-online skills@latest version
npm view --prefer-online @kisev/agentomatic@latest version
npm view --prefer-online @kisev/memomatic@latest version
npm view --prefer-online @kisev/reviewmatic@latest version
npm view --prefer-online @kisev/taskmatic@latest version

# Install and configure
npx --yes skills@latest add https://kisev.github.io/skills --global
npx --yes @kisev/agentomatic@latest install --global
npx --yes @kisev/agentomatic@latest config --global
npm install --global @kisev/memomatic
npm install --global @kisev/reviewmatic
npm install --global @kisev/taskmatic

# Local installation and active CLIs
npm list --prefix "$HOME/.config/opencode" @kisev/agentomatic --depth=0
npm list --global @kisev/memomatic @kisev/reviewmatic @kisev/taskmatic --depth=0
memomatic --version
reviewmatic --version
taskmatic --version
npx --yes skills@latest list --global
```

Всё на канале `dev` (движется после каждого успешного push в `dev`):

```shell
# Registry versions
npm view --prefer-online skills@latest version
npm view --prefer-online @kisev/agentomatic@dev version
npm view --prefer-online @kisev/memomatic@dev version
npm view --prefer-online @kisev/reviewmatic@dev version
npm view --prefer-online @kisev/taskmatic@dev version

# Install and configure
npx --yes skills@latest add https://kisev.github.io/skills/dev --global
npx --yes @kisev/agentomatic@dev install --global
npx --yes @kisev/agentomatic@dev config --global
npm install --global @kisev/memomatic@dev
npm install --global @kisev/reviewmatic@dev
npm install --global @kisev/taskmatic@dev

# Local installation and active CLIs
npm list --prefix "$HOME/.config/opencode" @kisev/agentomatic --depth=0
npm list --global @kisev/memomatic @kisev/reviewmatic @kisev/taskmatic --depth=0
memomatic --version
reviewmatic --version
taskmatic --version
npx --yes skills@latest list --global
```

Теги могут сдвинуться между просмотром и установкой. `npm list` проверяет
установленные пакеты, `--version` - CLI из PATH. npx не устанавливает CLI
глобально; `skills list` показывает локальные навыки, а не версию npm-установщика.

## Руководства

- [Переносимые навыки](docs/ru/how-to/portable-skills.md): установка в проект, обновление, очистка и диагностика. По умолчанию выбраны все среды `.agents/skills` и все навыки в списке; `--skill <name>` ограничивает выбор. См. [учебное руководство](docs/ru/tutorials/getting-started.md) и [каталог](docs/ru/reference/skill-catalog.md).
- [Интеграция OpenCode](docs/ru/how-to/opencode-integration.md): адаптеры команд, шесть ролей агентов, маршрутизация, диагностика, профили, сверка, необязательные `rules-injector`/`zed-bell` и стандартный `rtk` с `/rtk-stats`.
  Подтверждённая глобальная установка прописывает зависимость в `~/.config/opencode`, создавая `package.json` при необходимости; для области проекта запускайте из его корня без `--global`. Перезапустите OpenCode после активации или изменения компонентов.
- [Индекс документации](docs/ru/README.md): учебные материалы, практические инструкции, справочник и пояснения по Diataxis. [Сайт](https://kisev.github.io/skills) добавляет примеры работы скиллов и инструкции установки (`apps/docs-site`).

## Разработка

Общее [dev-окружение](dev/README.ru.md) запускает GitLab и Mattermost.
Опциональные проверки с настоящим сервером: [GitLab](tests/integration/gitlab/README.ru.md)
и [Mattermost](tests/integration/mattermost/README.ru.md). `task check` их не требует.

```shell
mise install
task install
task check
```

[Разработка](CONTRIBUTING.ru.md) · [Безопасность](SECURITY.ru.md) · [История выпусков](CHANGELOG.ru.md) · [Лицензия](LICENSE).
