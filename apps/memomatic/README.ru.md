# memomatic

[English version](README.md)

`@kisev/memomatic` — персональная обучающая память для агентов по архитектуре
памяти OpenClaw: ярусный Markdown-корпус, который можно читать как обычные файлы,
пересобираемый SQLite-индекс с FTS5 и опциональными локальными эмбеддингами и
ночной проход консолидации `dream`.

## Установка

```bash
npm install --global @kisev/memomatic
```

Корпус живёт в `$XDG_STATE_HOME/memomatic/` (`MEMORY.md`, `USER.md`, ежедневные
записи, `DREAMS.md`); правила — в `$XDG_CONFIG_HOME/memomatic/MEMORY_RULES.md`.
Нужен Node.js 22.13+. Подключите `memomatic mcp-serve` как локальный MCP-сервер stdio
в OpenCode, Kilo, MiMo или другом MCP-хосте и перезапустите хост. Плагин и
автоматическая подстановка контекста не используются. Фоновая обработка доступна через CLI:

```bash
memomatic process    # валидация inbox и индексация принятого (без модели)
memomatic dream      # полный проход: inbox + сессии + консолидация
```

Ночной проход планируют user-юниты systemd из `assets/systemd/`
(`memomatic-dream.service` и `memomatic-dream.timer`).

Перед извлечением сессий настройте `dream.model` и провайдера OpenCode;
без модели отметка обработанных сессий сохраняется. См.
[настройку, первую запись и расписание](../../docs/ru/how-to/memomatic.md).

## CLI и Dream

См. [соглашения CLI](../../docs/ru/reference/cli.md) и
[управление Dream](../../docs/ru/how-to/memomatic.md#наблюдение-ограничения-и-продолжение-dream).
`dream --plan` читает очередь без модели; `dream --dry-run` может вызывать модели.
Обычный Dream обрабатывает весь подходящий снимок с контрольными точками фрагментов,
переиспользуя один сервер OpenCode и неизменённые эмбеддинги. Первая миграция старого
курсора перепроверяет историю один раз, сохраняя накопленную память.

## Inbox

Все записи асинхронны. Скиллы, агенты и инструмент `memory_write` кладут
строки записей Markdown в `$XDG_STATE_HOME/memomatic/inbox/`:

```markdown
- Durable-вывод одним предложением. <!-- source: team-retro --> <!-- key: stable-id -->
```

Следующий проход `process` или `dream` валидирует дропы, применяет правила
`never-save`, дедуплицирует точные тексты, замещает записи с тем же `key`,
пересобирает SQLite-индекс с батч-эмбеддингами и переносит отклонённое в
`inbox/rejected/`. Продюсеры детектируют inbox по наличию и молча
пропускают дроп, если memomatic нет.

Каждая запись может нести аннотацию `source`. Из неё выводится видимость:
записи `team-*`, `gitlab` и `spec-manage` можно цитировать в командных
артефактах; остальные источники (`people-journal`, `stopit`,
`mattermost-triage`, `task-*`, `docs-*`, `user`) — personal-only. Метка
возвращается в поиске.

## Поверхности

- CLI `memomatic`: `process`, `dream`, `search`, `status`, `index`.
- MCP-сервер stdio с инструментами `memory_search`, `memory_get`,
  `memory_write` и `memory_forget`.

Модель сама инициирует поиск памяти через видимые MCP-вызовы. Dream отдельно
обрабатывает историю OpenCode; подключение другого хоста не импортирует его
сессии. Agentomatic и memomatic устанавливаются независимо.

Без явных директив, описанных в `MEMORY_RULES.md`, ничего не удаляется.
