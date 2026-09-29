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
- Необязательные обертки плагинов `rules-injector` и `zed-bell`;
  обертка сжатия `rtk` развертывается по умолчанию
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

- Состояние: `$XDG_STATE_HOME/memomatic/` (корпус, индекс, история, архив) и
  `$XDG_STATE_HOME/memomatic/inbox/`, куда скиллы и агенты кладут асинхронные
  Markdown-дропы.
- Настройки: `$XDG_CONFIG_HOME/memomatic/settings.json` (эндпоинт эмбеддера,
  модель и вариант мышления для сновидений, пороги) и `MEMORY_RULES.md` с ручными директивами:
  `- never-save: <тема>` и опциональная
  `- auto-clean: older-than=90d scope=episodic [source=name]`.
- Инструменты: `memory_search`, `memory_get`, `memory_write`, `memory_forget` -
  через отдельно установленный MCP-сервер stdio (`memomatic mcp-serve`).
  CLI предоставляет `process`, `search`, `status`, `index` и `dream --dry-run`.
  `memory_write` кладёт дроп в inbox и отвечает подсказкой flush; записи несут
  аннотацию `source`, из которой выводится видимость (`team-*`, `gitlab` и
  `spec-manage` цитируемы в командных артефактах, остальные personal-only);
  метка видна в поиске. Модель сама запрашивает память через инструменты;
  автоматической подстановки и плагина memomatic нет.
- Расписание: скопируйте `memomatic-sessions.service`, `memomatic-sessions.timer`,
  `memomatic-dream.service` и `memomatic-dream.timer` из
  `assets/systemd/` пакета `@kisev/memomatic` в `~/.config/systemd/user/` и выполните
  `systemctl --user enable --now memomatic-sessions.timer memomatic-dream.timer`;
  альтернативный запуск - командами `memomatic process`, `memomatic sessions`
  или `memomatic dream`.
- Забывание явно или по правилу: ничего не удаляется без `memory_forget` или
  директивы `auto-clean`; закрепленные записи не затухают.

Agentomatic не зависит от memomatic. См. [настройку MCP и переход со старого
плагина](../../docs/ru/how-to/memomatic.md).

## Требования

- Node.js 22 или новее.
- OpenCode `>=1.18.29 <1.19.0`.
- Постоянный npm-проект, которому принадлежит зависимость.

## Установка в проект

Запустите установщик из корня репозитория (добавьте `--global` для глобальной
области); подтверждённая установка также пропишет постоянную npm-зависимость:

```shell
npx --yes @kisev/agentomatic@latest install --dry-run
```

Укажите `@kisev/agentomatic@dev`, чтобы запустить dev-снимок.

Подтверждённая установка закрепляет исполняемую версию в ближайшем npm-проекте;
глобальная установка владеет `~/.config/opencode` и при необходимости создаёт
там `package.json`. В офлайн-окружении зависимость можно поставить вручную:
`npm install --save-exact @kisev/agentomatic`, затем запустить
`npx agentomatic install --dry-run` из этого проекта, чтобы версия исполнения
совпадала с установленным пакетом.
Примените изменение, повторив команду установки без `--dry-run` и подтвердив
напечатанную сводку плана, а вне терминала добавьте `--yes`.
Если выбрана основная интеграция, та же подтверждённая установка добавляет
`plugin` в пользовательскую конфигурацию OpenCode с сохранением существующих
записей. Отдельная команда `config` применяет дополнительные фрагменты
или повторяет неудавшийся шаг настройки:

```shell
npx agentomatic config --global --dry-run
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
