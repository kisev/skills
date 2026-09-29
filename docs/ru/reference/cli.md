---
audience: user
review: {"components": ["agentomatic", "memomatic", "taskmatic"], "sources": ["shared/references/cli_runtime.ts", "shared/manifest.json", "scripts/materialize_cli_runtime.mjs", "apps/memomatic/src/cli.ts", "apps/taskmatic/src/cli.ts", "packages/agentomatic/src/cli.ts"], "contracts": ["specs/requirements/interfaces/README.md"]}
---

# Соглашения командной строки

[English](../../reference/cli.md)

Agentomatic, memomatic и taskmatic требуют Node.js 22.13+. Все три используют
Commander для разбора параметров и общие CLI-утилиты, включаемые при сборке;
отдельный npm-пакет устанавливать не нужно. В agentomatic сохранены существующий
интерактивный мастер настройки и подробные инструкции команд.

## Справка и настройки

```shell
agentomatic install --help
memomatic dream --help
taskmatic claim --help
```

Справка и запрос версии не создают состояние приложения и не вызывают модель.
Справка перечисляет параметры, env-переменные, допустимые значения и примеры.
Неизвестные параметры вызывают ошибку, а не становятся поисковым текстом и не
запускают работу незаметно. `memomatic status` только читает состояние;
индексация выполняется явной командой `index`.

Приоритет: **аргументы CLI > env > JSON-конфигурация > значения по умолчанию**.
`--config FILE` выбирает JSON-файл; также доступны `AGENTOMATIC_CONFIG`,
`MEMOMATIC_CONFIG` и `TASKMATIC_CONFIG`. Общие ключи файла записываются в camelCase:
`logLevel`, `logFormat`, `progress`, `color`, `json`. Taskmatic также принимает
поля команд: `home`, `board`, `host`, `port`. Memomatic сохраняет секции `dream`,
`embedding`, `search`, `archive`. Параметры запуска вроде `--model` имеют
приоритет над `dream.model`. Эти переопределения не записываются в файл автоматически.

Имена env для параметров приложений указаны в справке: например,
`MEMOMATIC_MODEL`, `MEMOMATIC_TIMEOUT`, `TASKMATIC_AGENT`, `TASKMATIC_TTL`,
`TASKMATIC_HOST`, `AGENTOMATIC_MODEL`. `MEMOMATIC_HOME`/`--state-dir` и
`TASKMATIC_HOME`/`--home` задают абсолютные каталоги состояния. Стандартные XDG-пути
сохранены. Подтверждение `--yes` в agentomatic принимается только из CLI:
конфигурационный файл и `AGENTOMATIC_YES` не разрешают изменения.

## Результаты, логи и прогресс

| Параметр | Значения | Суффикс env |
| - | - | - |
| `--json` | Машинный результат | `_JSON` |
| `--log-level` | `debug`, `info`, `warn`, `error`, `silent` | `_LOG_LEVEL` |
| `--log-format` | `text`, `json` | `_LOG_FORMAT` |
| `--progress` | `auto`, `always`, `never` | `_PROGRESS` |
| `--color` | `auto`, `always`, `never` | `_COLOR` |

К суффиксу добавляется `AGENTOMATIC`, `MEMOMATIC` или `TASKMATIC`. По умолчанию
диагностика текстовая, уровня info; debug добавляет сообщения выполнения команд.
`NO_COLOR` отключает цвет. Автоматический прогресс рисуется только в терминале
через stderr; перенаправление и systemd получают последовательные строки.
JSON-логи не содержат анимации. Мастер agentomatic сохраняет управление терминалом;
дополнительная диагностика имеет уровень debug, а анимация без явного запроса отключена.

Результаты идут в stdout, диагностика — в stderr. В stdout MCP находятся только
сообщения протокола. Для обработки памяти memomatic сохраняет JSON-отчёты без TTY
и показывает краткий итог в терминале; `--json` выбирает JSON явно. Поиск и списки
задач сохраняют человекочитаемый вывод без `--json`. Существующие JSON-ошибки
agentomatic остаются в stdout ради совместимости.

Прогресс Dream показывает этап, прошедшее время и известное число фрагментов.
Для запроса модели процент не выдумывается: сообщение об ожидании выводится каждые
15 секунд до ответа или таймаута. Диагностика не печатает транскрипты, промпты,
тела ответов провайдера и данные авторизации.

## Коды завершения

Для memomatic и taskmatic: `0` — успех/справка, `2` — ошибка парсера, `1` — ошибка
операции или конфигурации, `124` — таймаут, `130` — прерывание. Agentomatic сохраняет
код ошибок `2` и специальные коды doctor. Отменённый Dream сохраняет завершённую
работу, но не считается успешно законченным проходом.

См. [управление Dream и восстановление](../how-to/memomatic.md) и
[команды Taskmatic](../how-to/taskmatic.md).
