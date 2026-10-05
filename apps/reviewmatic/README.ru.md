# reviewmatic

[English version](README.md)

`reviewmatic` - рантайм скилла `code-review` на Python. Он готовит ревью
GitLab merge request и локальных WIP-изменений, хранит приватные артефакты в
XDG и создаёт копируемые ручные runbook-файлы с командами `glab`. Он не
публикует изменения и не содержит терминальный интерфейс.

## Запуск из Git через uvx

Используйте тот же канал исходников, что и установленный скилл. Для стабильной
версии задайте точный тег выпуска (`vX.Y.Z`), для разработки используйте движущуюся
ветку `dev`. Перед запуском замените ref на существующий тег или ветку:

```shell
REVIEWMATIC_REF='<ref>'
uvx --from "git+https://github.com/kisev/skills.git@${REVIEWMATIC_REF}#subdirectory=apps/reviewmatic" reviewmatic --version
uvx --from "git+https://github.com/kisev/skills.git@${REVIEWMATIC_REF}#subdirectory=apps/reviewmatic" reviewmatic --help
```

Для dev-сборки задайте `REVIEWMATIC_REF=dev`. Используйте `uvx --refresh-package
reviewmatic --from "git+https://github.com/kisev/skills.git@${REVIEWMATIC_REF}#subdirectory=apps/reviewmatic"
reviewmatic --version`, чтобы обновить кэш исходников и сборки. `uvx` создаёт
временное окружение инструмента; `uv tool install` и публикация в PyPI не
нужны. Внешние runtime-инструменты: Git и `glab`.

Кэш uv содержит исполняемый пакет, а не артефакты ревью. Очистка кэша не
удаляет черновики и `runbook.md` из настроенного каталога XDG. Следующий вызов
После `uv cache clean` снова запустите выбранный ref:

```shell
uvx --from "git+https://github.com/kisev/skills.git@${REVIEWMATIC_REF}#subdirectory=apps/reviewmatic" reviewmatic --version
```

Это пересоберёт рантайм, но сохранит состояние XDG. Чтобы после ремонта
заново создать runbook, запустите `repair-review` через тот же источник
`uvx --from`, затем выполните возвращённую команду продолжения `finish-review`
через тот же источник.

## Разработка и сборка

```shell
task reviewmatic:check
task reviewmatic:install-smoke
uv build
```

Wheel и source distribution - стандартные Python-артефакты. Runtime-зависимостей
нет; требуется Python 3.12+. Install-smoke собирает локальный Git-снимок, wheel
и source distribution вне checkout, затем запускает их в изолированных
окружениях `uvx` без Node, `PYTHONPATH` и постоянной установки `reviewmatic`.

## Канонический переносимый рантайм

`src/reviewmatic/portable/` материализуется байт-в-байт из
`shared/references/` по секции `pythonRuntime` в `shared/manifest.json`. Меняйте
общий источник, затем выполняйте `task generate` и `task generate:check`. Не
редактируйте материализованную копию напрямую.

33 закоммиченные golden-фикстуры сохраняют контрактные ожидания, созданные из
TypeScript-ревизии
`3e409c217e94d643f77eb543caab9a2ed4b7288d`. Приложение и генератор TypeScript
удалены. `test_golden_parity.py` пересчитывает каждый дайджест, вердикт и
переход состояния относительно зафиксированных ожиданий; он не генерирует
ожидания из Python и не пропускает утверждения. См.
[`docs/reviewmatic-test-matrix.md`](../../docs/reviewmatic-test-matrix.md): там
описаны исходный baseline тестов и соответствие переноса.
