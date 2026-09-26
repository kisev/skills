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
memomatic dream --dry-run
```

Ночной проход планируют user-юниты systemd из `assets/systemd/`
(`memomatic-dream.service` и `memomatic-dream.timer`).

## Поверхности

- CLI `memomatic`: инспекция корпуса и проход `dream`.
- MCP-сервер stdio с инструментами `memory_search`, `memory_get`,
  `memory_write` и `memory_forget`.
- Плагин OpenCode, реэкспортируемый пакетом `@kisev/agentomatic`.

Без явных директив, описанных в `MEMORY_RULES.md`, ничего не удаляется.
