# Документация

[English](../README.md)

Выберите раздел по задаче, которую нужно решить. У Portable Agent Skills и
`skills-opencode` разные installation и update lifecycle; инструкции явно
сохраняют эту границу.

## Tutorials

- [Начало работы с portable skills](tutorials/getting-started.md) - установка
  stable distribution для Codex и OpenCode и проверка результата.

## How-to guides

- [Управление portable skills](how-to/portable-skills.md) - установка по scope или
  host, обновление, смена старого source, очистка retired names и диагностика.
- [Установка и управление skills-opencode](how-to/opencode-integration.md) -
  установка package, выбор assets, активация plugin, обновление, reconcile,
  диагностика, настройка agents и безопасное удаление.
- [Участие в разработке](../../CONTRIBUTING.ru.md) - изменение authored sources и
  запуск обязательных checks.

## Reference

- [Каталог skills](reference/skill-catalog.md) - active skills, требования,
  командные profiles и границы external tools.
- [Инвентарь миграции](migration-inventory.md) - active и retired names,
  replacements, package surfaces и ownership records.
- [Проверка](verification.md) - проверяемые release contracts и quality gates.
- [Политика безопасности](../../SECURITY.md) - порядок сообщения об уязвимостях.
- [История выпусков](../../CHANGELOG.md) - опубликованные изменения по версиям.

## Explanation

- [Архитектура](architecture.md) - границы source of truth, build и distribution,
  host integration, runtime behavior и инварианты.
- [Каноническая спецификация](../../specs/README.md) - нормативные требования,
  architecture decisions и capability contracts для maintainers.
