---
audience: user
review: {"components": ["memomatic"], "sources": ["apps/memomatic/src/*", "apps/memomatic/test/*", "apps/memomatic/assets/systemd/*", "packages/agentomatic/src/plugins/memomatic.ts", "packages/agentomatic/src/installer.ts"], "contracts": ["specs/capabilities/plugins/memomatic.md"]}
---

# Настройка и использование Memomatic

[English](../../how-to/memomatic.md)

## Установка и подключение

Нужны Node.js 22+ и npm. Для CLI, доступного за пределами npm-проекта:

```shell
npm install --global @kisev/memomatic
memomatic --version
```

Для локальной установки используйте `npm install @kisev/memomatic` и вызывайте
CLI через `npx memomatic`. Пример systemd ниже рассчитан на глобальный бинарник.

В [установщике agentomatic](opencode-integration.md) явно выберите обёртку
`memomatic`: по умолчанию выбрана только `rtk`. Перезапустите OpenCode и проверьте
доступность `memory_write`, `memory_search`, `memory_get` и `memory_forget`.
Другие MCP-хосты могут запускать `memomatic mcp-serve` как локальный stdio-сервер.

Глобальный CLI и npm-зависимость плагина установлены отдельно.
`@dev` выбирает последнюю успешную публикацию из `dev` для всех workspace-пакетов:
`@kisev/agentomatic`, `@kisev/memomatic` и `@kisev/safe-fs`.
`@latest` - канал стабильных релизов; до первого стабильного релиза пакета его
первоначальный тег в реестре может ещё указывать на prerelease. Для dev-установок
явно указывайте `@dev`:

```shell
npm install --global @kisev/memomatic@dev
npx --yes @kisev/agentomatic@dev install --global
```

Проверьте, что версия CLI совпадает с зависимостью `@kisev/memomatic` у плагина:
обновление agentomatic не обновляет глобальный CLI. Если между командами канал
`dev` обновился, установите ту же точную версию memomatic.

## Первая запись и поиск

Попросите агента вызвать `memory_write` с `text: "Use a separate preview before publishing."`
и `source: "user"`. Результат указывает на файл в очереди inbox, а не на проиндексированный факт.
Затем выполните:

```shell
memomatic process
memomatic search "preview publishing"
```

Вызовите `memory_get` с полученными файлом и строкой для чтения полной записи.
Результаты поиска указывают источник и личную или командную видимость. Личную запись
нельзя копировать в общие артефакты. `memory_forget` удаляет одну явно выбранную
строку; обычная модельная консолидация не разрешает удалять кураторскую память.

## Настройка Dream

Перед извлечением знаний из сессий установите OpenCode, настройте провайдера
и выберите доступную модель через `opencode models`. Создайте
`${XDG_CONFIG_HOME:-$HOME/.config}/memomatic/settings.json` с выбранным
идентификатором `provider/model`:

```json
{"dream": {"model": "provider/model"}}
```

```shell
memomatic dream --dry-run
memomatic dream
```

Предпросмотр сохраняет файлы памяти, постоянный индекс и отметку обработанных
сессий; настроенные вызовы модели и эмбеддингов могут выполняться. Без модели
`dream` обрабатывает inbox, но не извлекает сессии и не продвигает их отметку.
Для прохода inbox без модели используйте `process`. Невалидный ответ консолидации
включает ограниченное добавление записей с сохранением существующей кураторской памяти.

Dream читает сессии OpenCode, включая текст из отдельной таблицы `part`.
MCP-подключения в других хостах используют общие явные записи памяти, но не
импортируют историю сессий этих хостов. Вызовы модели используют позиционный
аргумент сообщения OpenCode и JSON-события в выводе. Перед включением таймера
сопоставьте `sessionsIngested` с доступными необработанными сессиями: проход с нулём
сессий не проверяет доступ к модели.

## Настройка локальных эмбеддингов

Эмбеддинги необязательны и по умолчанию отключены. Без них память использует
текстовый поиск FTS5. Для векторного поиска через Ollama запустите Ollama и
установите embedding-модель, например `qwen3-embedding:4b`, затем добавьте в
`settings.json` рядом с `dream` этот блок:

```json
{
  "embedding": {
    "url": "http://127.0.0.1:11434/v1/embeddings",
    "model": "qwen3-embedding:4b"
  }
}
```

URL должен указывать на OpenAI-совместимый endpoint эмбеддингов, а не на
`/api/embed` Ollama. Memomatic отправляет туда текст записей и запросов; loopback-адрес
оставляет запросы эмбеддингов локальными. Задавать размерность не нужно.
После смены модели выполните `memomatic index`, затем проверьте `memomatic search`.
Endpoint должен быть доступен при индексации и поиске: сбой запроса эмбеддингов
возвращает ошибку, а не включает незаметно текстовый поиск.

## Хранение, очистка и восстановление

Корпус находится в `${XDG_STATE_HOME:-$HOME/.local/state}/memomatic/`:
`MEMORY.md`, `USER.md`, ежедневные файлы в `memory/`, `DREAMS.md`, `inbox/`,
`history/` и `archive/`. Правила находятся в
`${XDG_CONFIG_HOME:-$HOME/.config}/memomatic/MEMORY_RULES.md`.

```markdown
- never-save: credentials
- auto-clean: older-than=90d scope=episodic source=stopit
```

Очистка архивирует только подходящие старые незакреплённые записи и сохраняет
остальные записи того же файла. Отклонённые файлы inbox остаются в `inbox/rejected/`.
Проверяйте их после отказа. Чтобы отменить нежелательное изменение, найдите
предыдущее содержимое по хэшу в `history/` или выбранные записи в `archive/`,
восстановите нужный текст корпуса и выполните `memomatic index`. Эти данные
должны оставаться приватными и вне Git.

## Запуск по расписанию

Юниты принадлежат `@kisev/memomatic`, а не agentomatic. Найдите их через
`npm root --global`, затем скопируйте оба юнита из
`<npm-root>/@kisev/memomatic/assets/systemd/` в `~/.config/systemd/user/`.
Убедитесь, что пользовательский сервис находит `memomatic` и `opencode`; задайте
абсолютные пути или явный PATH сервиса, если бинарники предоставляет менеджер версий оболочки.

```shell
systemctl --user daemon-reload
systemctl --user enable --now memomatic-dream.timer
systemctl --user status memomatic-dream.timer
journalctl --user -u memomatic-dream.service
```

Включайте таймер после успешного ручного прохода. Команда
`systemctl --user disable --now memomatic-dream.timer` отключает расписание и сохраняет память.
