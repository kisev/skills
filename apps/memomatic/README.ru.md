# memomatic

[English version](README.md)

`@kisev/memomatic` — персональная обучающая память для агентов по архитектуре
памяти OpenClaw: ярусный Markdown-корпус, который можно читать как обычные файлы,
пересобираемый SQLite-индекс с FTS5 и опциональными локальными эмбеддингами и
ночной проход консолидации `dream`.

## Установка

```bash
npm install @kisev/memomatic
```

Корпус живёт в `$XDG_STATE_HOME/memomatic/` (`MEMORY.md`, `USER.md`, ежедневные
записи, `DREAMS.md`); правила — в `$XDG_CONFIG_HOME/memomatic/MEMORY_RULES.md`.
Установщик `@kisev/agentomatic` разворачивает плагин OpenCode автоматически;
автономное использование — через CLI:

```bash
memomatic process    # валидация inbox и индексация принятого (без модели)
memomatic dream      # полный проход: inbox + сессии + консолидация
```

Ночной проход планируют user-юниты systemd из `assets/systemd/`
(`memomatic-dream.service` и `memomatic-dream.timer`).

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
возвращается в поиске и в bootstrap-блоках сессий.

## Поверхности

- CLI `memomatic`: `process`, `dream`, `search`, `status`, `index`.
- MCP-сервер stdio с инструментами `memory_search`, `memory_get`,
  `memory_write` и `memory_forget`.
- Плагин OpenCode, реэкспортируемый пакетом `@kisev/agentomatic`; его
  bootstrap добавляет к кураторской памяти блоки напоминаний по проекту и
  trigger-фразам (контекст сессии и маппинг `projects` из `settings.json`).

Без явных директив, описанных в `MEMORY_RULES.md`, ничего не удаляется.
