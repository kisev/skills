# Agent Skills

[English](README.md)

Переносимые навыки для Codex, Claude и OpenCode, где `skillmate` — единый установщик-конфигуратор.

## Компоненты проекта

| Компонент | Что даёт | Жизненный цикл |
| - | - | - |
| Переносимые навыки | 44 самодостаточных сценария для разработки, документации, поставки и командной работы | Устанавливаются через `skillmate` или стабильный CLI `skills@latest` в каталог навыков хоста |
| `skillmate` | Одна команда для установки навыков, командных поверхностей и настройки Codex, Claude и OpenCode в проектной или глобальной области | Поставляется через PyPI: `uvx skillmate` или `pip install skillmate` |

CLI `skills` (канал `npx skills`) устанавливает переносимые навыки из того же дистрибутива Pages; `skillmate` добавляет размещение по хостам с диалектами, командные поверхности и модель безопасности «превью — подтверждение».

## Установите всё

Установите переносимые навыки, `skillmate`, [memomatic](docs/ru/how-to/memomatic.md), [reviewmatic](apps/reviewmatic/README.ru.md) и [taskmatic](docs/ru/how-to/taskmatic.md); повторный запуск команд обновляет их. Reviewmatic запускается через `uvx` из репозитория, не через npm или PyPI.
`skillmate install` показывает полный план и пишет только после подтверждения (`--yes` пропускает вопрос). После обновлений перезапустите хосты.

Навыки через `skillmate`, стабильный канал:

```shell
# Версия дистрибутива
uvx skillmate status

# Установить в проект для всех трёх хостов
uvx skillmate install --yes

# Или глобально, или для выбранных хостов и навыков
uvx skillmate install --scope global --hosts claude,opencode --yes
uvx skillmate doctor
```

Навыки через CLI `skills` (тот же дистрибутив, совместимый канал):

```shell
npm view --prefer-online skills@latest version
npx --yes skills@latest add https://kisev.github.io/skills --global
npx --yes skills@latest update --global
npx --yes skills@latest list --global
```

Reviewmatic с точного релизного рефа:

```shell
REVIEWMATIC_REF='<ref>' # используйте точный релизный тег стабильного канала навыков
uvx --from "git+https://github.com/kisev/skills.git@${REVIEWMATIC_REF}#subdirectory=apps/reviewmatic" reviewmatic --version
```

На dev-канале установите из чекаута репозитория — реестр не участвует:

```shell
skillmate install --from-checkout /path/to/skills --yes   # неопубликованное содержимое рабочего дерева
REVIEWMATIC_REF=dev # подвижная ветка разработки, совпадает с dev-каналом навыков
uvx --refresh-package reviewmatic --from "git+https://github.com/kisev/skills.git@${REVIEWMATIC_REF}#subdirectory=apps/reviewmatic" reviewmatic --version
```

`skillmate status` показывает установленные версии по хостам и областям;
`--version` закрепляет точную версию дистрибутива. `uvx` запускает
reviewmatic эфемерно с выбранного Git-рефа и не устанавливает глобальный
инструмент. `--version` печатает выровненную релизную версию: на точном
релизном теге она совпадает с тегом, на подвижной ветке `dev` остаётся на
последней выпущенной версии между релизами. `reviewmatic runtime-info`
дополнительно сообщает Git-коммит установленных исходников. `skills list`
показывает установленные навыки.

## Проверьте контракт окружения

Некоторым навыкам нужны внешние инструменты: `git`, `glab`, `uv`/`uvx` или npm-приложение (например, `code-review`, `mr-prepare` или `taskmatic`). Каждый архив с такой зависимостью несёт материализованный `references/requirements.json` со списком инструментов, командами проверки и готовыми командами установки, а также `source_revision` дистрибутива. Запустите встроенную проверку на стандартной библиотеке в первой сессии и покажите вывод; она ничего не устанавливает и не обращается в сеть:

```shell
python3 ~/.agents/skills/code-review/scripts/check_environment.py
```

Каждая строка — `OK` или `FAIL`, для каждого сбоя печатается точная команда починки. `skillmate doctor` читает те же манифесты для глобальной и проектной областей и сообщает отсутствующие файлы, расхождение версий, чужие файлы и команды ремонта.

## Руководства

- [Установка и управление навыками](docs/ru/how-to/install-skills.md): хосты, области, командные поверхности, обновления, удаление и режим dev-чекаута. См. [учебник](docs/ru/tutorials/getting-started.md) и [каталог](docs/ru/reference/skill-catalog.md).
- [Переносимые навыки](docs/ru/how-to/portable-skills.md): проектные установки, обновления, очистка и диагностика через CLI `skills`. По умолчанию выбраны все хосты `.agents/skills`; селектор предвыбирает все навыки. Ограничьте выбор через `--skill <name>`. Обновляйте глобальную установку интерактивно через `npx --yes skills@latest update --global`, чтобы устаревшие имена предлагалось удалить.
- [Индекс документации](docs/ru/README.md): Diataxis — учебные материалы, практические руководства, справочник, объяснения. На [сайте](https://kisev.github.io/skills) есть примеры взаимодействия с навыками и инструкции по установке (`apps/docs-site`).

## Разработка

Общая [среда разработки](dev/README.ru.md) поднимает GitLab и Mattermost.
Необязательные проверки на реальных серверах: [GitLab](tests/integration/gitlab/README.ru.md) и
[Mattermost](tests/integration/mattermost/README.ru.md). Для `task check` они не нужны.

```shell
mise install
task install
task check
```

[Вклад](CONTRIBUTING.ru.md) · [Безопасность](SECURITY.ru.md) · [История изменений](CHANGELOG.ru.md) · [Лицензия](LICENSE).
