# Интеграция с OpenCode

[English](README.md)

`@kisev/agentomatic` - полноценный компонент Agent Skills для OpenCode. Он
дополняет переносимые навыки, но имеет собственный жизненный цикл установки,
обновления и удаления.

## Что добавляет пакет

- Адаптеры слеш-команд OpenCode для установленных переносимых навыков.
- Шесть агентов с фиксированными ролями: `manager`, `architect`, `mapper`, `worker`,
  `review` и `critic`.
- Маршрутизация по возможностям и прямой CLI для `doctor`, `reconcile` и
  управления профилями агентов.
- Команда `config` с подтверждением: подключает пакет и рекомендованные
  фрагменты в `opencode.json(c)`, `tui.json`, `kilo.json(c)` и
  `mimocode.json(c)`, сохраняя существующие записи и комментарии.
- Необязательные обертки плагинов `rules-injector`, `zed-bell` и персональная
  обучающая память `memomatic`; обертка сжатия `rtk` развертывается по умолчанию
  и наблюдаема через `/rtk-stats` и `doctor`.

Пакет не содержит, не устанавливает, не обновляет, не проверяет и не удаляет
переносимые навыки. Их жизненным циклом управляет CLI `skills`.

## Memomatic

Memomatic - персональная обучающая память по мотивам архитектуры OpenClaw:
ярусный Markdown (`MEMORY.md`, `USER.md`, ежедневные записи, `DREAMS.md`),
пересобираемый SQLite-индекс с полнотекстовым поиском FTS5 и опциональными
локальными эмбеддингами, а также ночной проход сновидений, который инжестит
транскрипты сессий, продвигает стабильно полезные записи детерминированными
воротами и одной ограниченной модельной фазой, замещает устаревшие факты по
ключу и сохраняет все предобразы.

- Состояние: `$XDG_STATE_HOME/memomatic/` (корпус, индекс, история, архив).
- Настройки: `$XDG_CONFIG_HOME/memomatic/settings.json` (эндпоинт эмбеддера,
  модель и вариант мышления для сновидений, пороги) и `MEMORY_RULES.md` с
  ручными директивами: `- never-save: <тема>` и опциональная
  `- auto-clean: older-than=90d scope=episodic`.
- Инструменты: `memory_search`, `memory_get`, `memory_write`, `memory_forget` -
  через плагин, MCP-сервер stdio (`agentomatic-memomatic mcp-serve`) и CLI
  (`search`, `status`, `index`, `dream --dry-run`).
- Расписание: скопируйте `memomatic-dream.service` и `memomatic-dream.timer` из
  `assets/systemd/` пакета в `~/.config/systemd/user/` и выполните
  `systemctl --user enable --now memomatic-dream.timer`; альтернативный запуск -
  командой `agentomatic-memomatic dream`.
- Забывание явно или по правилу: ничего не удаляется без `memory_forget` или
  директивы `auto-clean`; закрепленные записи не затухают.

## Требования

- Node.js 22 или новее.
- OpenCode `>=1.18.29 <1.19.0`.
- Постоянный npm-проект, которому принадлежит зависимость.

## Установка в проект

Установите пакет в npm-проект репозитория и предварительно просмотрите
управляемые файлы:

```shell
npm install --save-exact @kisev/agentomatic
npx --yes @kisev/agentomatic@latest install --dry-run
```

Выполните точную команду подтверждения, которую выведет предварительный просмотр.
Если для выбранных файлов нужна основная интеграция, подключите пакет в
пользовательскую конфигурацию OpenCode вручную или подтвержденной командой
`config`, которая добавляет запись `plugin` с сохранением существующих записей:

```shell
npx --yes @kisev/agentomatic@latest config --global --dry-run
```

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["@kisev/agentomatic"]
}
```

Перезапустите OpenCode после активации или изменения файлов. Команды `install` и
`uninstall` не редактируют `opencode.json`; `config` - единственный
подтвержденный путь для фрагментов конфигурации, а выбор адаптеров команд не
устанавливает переносимые навыки.

## Документация

Каноническая документация находится в `docs/`, а не в исходном коде пакета:

- [Полная инструкция по интеграции OpenCode](https://github.com/kisev/skills/blob/main/docs/ru/how-to/opencode-integration.md)
- [Инструкция по переносимым навыкам](https://github.com/kisev/skills/blob/main/docs/ru/how-to/portable-skills.md)
- [Индекс документации](https://github.com/kisev/skills/blob/main/docs/ru/README.md)

Полная инструкция описывает глобальную установку, выбор файлов, подтверждение,
активацию, фрагменты `config`, `doctor`, обновление, `reconcile`, профили
агентов, владение файлами и удаление.
