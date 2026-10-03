# memomatic

[English version](README.md)

`@kisev/memomatic` — персональная обучающая память для агентов по архитектуре
памяти OpenClaw: ярусный Markdown-корпус, который можно читать как обычные файлы,
пересобираемый SQLite-индекс с FTS5 и опциональными локальными эмбеддингами,
проход извлечения `sessions` и ночной проход консолидации `dream`.

## Установка

```bash
# Registry version
npm view --prefer-online @kisev/memomatic@latest version

# Install
npm install --global @kisev/memomatic

# Installed package and active CLI
npm list --global @kisev/memomatic --depth=0
memomatic --version
```

Тег может сдвинуться между просмотром и установкой; последние команды показывают
установленный пакет и CLI из PATH. Для dev-канала укажите `@dev` и в просмотре,
и в установке.

Корпус живёт в `$XDG_STATE_HOME/memomatic/` (`MEMORY.md`, `USER.md`, ежедневные
записи, `DREAMS.md`); правила — в `$XDG_CONFIG_HOME/memomatic/MEMORY_RULES.md`.
Нужен Node.js 22.13+. Подключите `memomatic mcp-serve` как локальный MCP-сервер stdio
в OpenCode, Kilo, MiMo или другом MCP-хосте и перезапустите хост. Плагин и
автоматическая подстановка контекста не используются. Фоновая обработка доступна через CLI:

```bash
memomatic process    # валидация inbox и индексация принятого (без модели)
memomatic sessions   # извлечение эпизодической памяти из сессий OpenCode (модель)
memomatic dream      # консолидация: inbox + продвижение + перезапись + архив
```

Ночные проходы планируют user-юниты systemd из `assets/systemd/`
(`memomatic-sessions.service`/`.timer` для извлечения и
`memomatic-dream.service`/`.timer` для консолидации).

Перед извлечением сессий настройте `sessions.model` (или оставьте старый
`dream.model`) и провайдера OpenCode V2; без модели отметка обработанных сессий
сохраняется. Извлечение сессий и его сервер модели требуют OpenCode `2.x`;
база сессий до V2 не разбирается. См.
[настройку, первую запись и расписание](../../docs/ru/how-to/memomatic.md).

## CLI, Sessions и Dream

См. [соглашения CLI](../../docs/ru/reference/cli.md) и
[управление Dream](../../docs/ru/how-to/memomatic.md#наблюдение-ограничения-и-продолжение-dream).
`sessions --plan` читает очередь сессий без модели; `dream --plan` считает
ожидающие файлы inbox и кандидатов на продвижение. `--dry-run` показывает
превью любой команды и может вызывать модели. Sessions обрабатывают весь
подходящий снимок с контрольными точками фрагментов, переиспользуя один сервер
OpenCode и неизменённые эмбеддинги; Dream затем продвигает эпизодические записи,
прошедшие пороги использования, в `MEMORY.md` через ограниченную консолидацию и
архивирует старое. Первая миграция старого курсора перепроверяет историю один
раз, сохраняя накопленную память. `status` показывает очередь: ожидающие файлы
inbox, бэклог сессий, кандидатов на продвижение и время последнего прохода.

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
артефактах; остальные источники (`people-journal`, `handoff`,
`mattermost-triage`, `task-*`, `docs-*`, `user`) — personal-only. Метка
возвращается в поиске.

## Поверхности

- CLI `memomatic`: `process`, `sessions`, `dream`, `search`, `status`, `index`.
- MCP-сервер stdio с инструментами `memory_search`, `memory_get`,
  `memory_write` и `memory_forget`.

Модель сама инициирует поиск памяти через видимые MCP-вызовы. Команда
`sessions` отдельно обрабатывает историю OpenCode; подключение другого хоста
не импортирует его сессии. Agentomatic и memomatic устанавливаются независимо.

Без явных директив, описанных в `MEMORY_RULES.md`, ничего не удаляется.
