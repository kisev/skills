# Agent Skills

[English](README.md)

Переносимые навыки для агентов Codex и OpenCode, а также `agentomatic` -
полноценная интеграция с OpenCode; компоненты независимы и используются по отдельности.

## Компоненты проекта

| Компонент | Назначение | Жизненный цикл |
| - | - | - |
| Portable Agent Skills | 38 автономных сценариев для разработки, документации, выпуска и командной работы | Стабильный CLI `skills@latest` устанавливает их в `~/.agents/skills` или `.agents/skills` |
| `@kisev/agentomatic` | Команды OpenCode, агенты с фиксированными ролями, средства маршрутизации, диагностика и необязательные обёртки плагинов | Устанавливается как зависимость npm; управляемые файлы находятся в `~/.config/opencode` или `.opencode` |

Переносимые навыки не требуют npm-пакета. Пакет не содержит, не устанавливает и
не обновляет, не проверяет и не удаляет их. Их жизненным циклом управляет CLI
`skills`.

## Установка всего

Полная настройка: переносимые навыки, `agentomatic` и пользовательские
приложения [memomatic](docs/ru/how-to/memomatic.md) (память агента) и
[taskmatic](docs/ru/how-to/taskmatic.md) (доска задач). Для обновления
повторите те же команды. `install` и `config` печатают план и запрашивают
подтверждение в терминале, а вне его принимают флаги выбора с `--yes`; до
первого стабильного релиза тег `latest` указывает на пререлиз. Перезапустите
OpenCode и другие запущенные среды, включая MCP-хосты и веб-доску taskmatic.

Всё на канале `latest`:

```shell
npx --yes skills@latest add https://kisev.github.io/skills --global
npx --yes @kisev/agentomatic@latest install --global
npx --yes @kisev/agentomatic@latest config --global
npm install --global @kisev/memomatic
npm install --global @kisev/reviewmatic
npm install --global @kisev/taskmatic
```

Всё на канале `dev` (движется после каждого успешного push в `dev`):

```shell
npx --yes skills@latest add https://kisev.github.io/skills/dev --global
npx --yes @kisev/agentomatic@dev install --global
npx --yes @kisev/agentomatic@dev config --global
npm install --global @kisev/memomatic@dev
npm install --global @kisev/reviewmatic@dev
npm install --global @kisev/taskmatic@dev
```

## Переносимые навыки

По умолчанию навыки ставятся для всех сред, читающих `.agents/skills`,
включая Codex и OpenCode; установщик открывает список с предвыбранными
позициями, снимите лишнее или передайте `--skill <name>`. Начните с
[пошаговой установки](docs/ru/tutorials/getting-started.md), используйте
[инструкцию по переносимым навыкам](docs/ru/how-to/portable-skills.md) для
установки в проект, обновления и очистки или откройте
[каталог навыков](docs/ru/reference/skill-catalog.md).

## agentomatic

`@kisev/agentomatic` добавляет в OpenCode:

- адаптеры слеш-команд для установленных навыков;
- шесть агентов с фиксированными ролями и управление профилями;
- маршрутизацию по возможностям и прямой CLI для установки, диагностики,
  профилей и сверки;
- необязательные обёртки плагинов `rules-injector` и `zed-bell`, а также
  обёртка сжатия `rtk`, включённая по умолчанию и наблюдаемая через
  `/rtk-stats`.

Глобальная установка владеет npm-проектом в `~/.config/opencode` и при
необходимости создаёт там `package.json`; для области проекта запустите
установщик из корня проекта без `--global`. Подтверждённая установка также
прописывает постоянную npm-зависимость, через которую резолвится плагин.
Перезапустите OpenCode после активации и следуйте полной
[инструкции по интеграции OpenCode](docs/ru/how-to/opencode-integration.md).

## Документация

[Индекс документации](docs/ru/README.md) организует учебные материалы,
практические инструкции, справочник и поясняющие материалы по Diataxis.
[Сайт документации](https://kisev.github.io/skills) показывает каталог скиллов,
примеры взаимодействия и инструкции установки (`apps/docs-site`).

## Разработка

```shell
mise install
task install
task check
```

Дополнительные сведения:

- [CONTRIBUTING.ru.md](CONTRIBUTING.ru.md) - правила работы с исходным кодом и
  проверки для отдельных изменений.
- [SECURITY.ru.md](SECURITY.ru.md) - порядок сообщения об уязвимостях.
- [CHANGELOG.ru.md](CHANGELOG.ru.md) - история выпусков.
- [LICENSE](LICENSE) - условия лицензии.
