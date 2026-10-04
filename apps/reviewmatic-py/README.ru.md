# reviewmatic (порт на Python)

[English version](README.md)

Python-реализация GitLab-review CLI reviewmatic. Этап 1 порта поставляет
каркас пакета, полную поверхность команд TypeScript-CLI (`apps/reviewmatic`)
и каноническое контрактное ядро — без бизнес-логики обзора.

## Установка и запуск

Пакет собирается и запускается из репозитория через uv:

```shell
uv run --locked reviewmatic --version
uv run --locked reviewmatic --help
uv build
```

Имя `reviewmatic` на PyPI закреплено за этим пакетом; публикация выполняется
на более позднем этапе.

## Объем этапа

Этап 1 реализует контрактные операции, которые канонический рантайм
полностью покрывает: `capabilities`, `assess-mode`, исторический стаб
`publication` и `marker-run`. Остальные подкоманды разбирают аргументы так
же, как TypeScript-CLI, и отвечают явным конвертом not-implemented с кодом
выхода 5; бизнес-логика появится на этапе 2.

Коды выхода следуют контракту TypeScript: `0` — успех, `1` — неожиданный
сбой, `2` — некорректный ввод или блокировка, `3` — инструмент недоступен,
`4` — неподдерживаемый режим, `5` — не реализовано на этапе 1.

## Каноническое контрактное ядро

Каталог `src/reviewmatic/portable/` материализуется байт-в-байт из
канонических источников `shared/references/` (`shared/manifest.json`, секция
`pythonRuntime`). Не редактируйте эти файлы: меняйте канон, затем выполняйте
`task generate` и проверяйте через `task generate:check`.

Паритет дайджестов с TypeScript-реализацией держат закоммиченные golden-
фикстуры в `tests/golden/`. Их генерирует `task reviewmatic-py:fixtures` из
реальных TypeScript-источников, а `task generate:check` проверяет побайтово;
Python-тесты паритета падают при любом расхождении.

## Разработка

```shell
uv run --locked pytest
uv run --locked mypy
uv run --locked ruff check .
```

Локальный `pyproject.toml` приложения повторяет выбор линтов репозитория и
несёт per-file-ignores материализованных канонических модулей.
