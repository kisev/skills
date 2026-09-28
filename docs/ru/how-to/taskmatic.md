---
audience: user
review: {"components": ["taskmatic"], "sources": ["skills/taskmatic/scripts/*", "apps/taskmatic/src/taskmatic_web/*", "apps/taskmatic/tests/*"], "contracts": ["specs/capabilities/skills/taskmatic.md"]}
---

# Создание и использование доски Taskmatic

[English](../../how-to/taskmatic.md)

## Установка и создание базы

Нужен Python 3.12+. Установите скилл `taskmatic` по
[инструкции для переносимых скиллов](portable-skills.md). Задайте `TASKMATIC_SKILL`
как каталог установленного скилла с `SKILL.md`, затем создайте первую карточку:

```shell
python3 "$TASKMATIC_SKILL/scripts/taskmatic.py" add "Check the first board" --board main
python3 "$TASKMATIC_SKILL/scripts/taskmatic.py" list --board main
```

Раннер создаёт приватную SQLite-базу и производные экспорты. Отдельное
веб-приложение не создаёт отсутствующую базу: сначала создайте карточку.
Оба инструмента должны использовать один абсолютный `TASKMATIC_HOME` или стандартный
`${XDG_STATE_HOME:-$HOME/.local/state}/agent-skills/taskmatic/`.

## Работа с карточками

Замените `CARD_ID` идентификатором из результата создания или списка:

```shell
python3 "$TASKMATIC_SKILL/scripts/taskmatic.py" show CARD_ID
python3 "$TASKMATIC_SKILL/scripts/taskmatic.py" claim CARD_ID --agent review-bot --ttl 30m
python3 "$TASKMATIC_SKILL/scripts/taskmatic.py" note CARD_ID "Checked the setup" --actor review-bot
python3 "$TASKMATIC_SKILL/scripts/taskmatic.py" complete CARD_ID
```

Статусы: `todo`, `doing`, `review`, `blocked`, `done`. Действующий захват
другого агента нельзя перехватить; продлевайте свой захват при долгой работе и освобождайте
при блокировке. [Workflow раннера](../../../skills/taskmatic/references/workflow.md)
описывает редактирование, дочерние карточки, фильтры и захваты. Завершение снимает захват.

## Просмотр доски

```shell
uv tool install git+https://github.com/kisev/skills#subdirectory=apps/taskmatic
taskmatic-web serve
```

Откройте `http://127.0.0.1:8765`. Параметр `--port 0` выбирает свободный порт. Адреса
вне loopback отклоняются; у доски нет аутентификации для сетевого доступа. Карточки и
захваты меняются только через раннер или MCP. Без приложения можно открыть производный
`export/web/index.html`; он обновляется только при повторном экспорте.

## Подключение агента

Для OpenCode добавьте блок в пользовательскую конфигурацию, заменив placeholder
каталогом установленного скилла с `SKILL.md`, затем перезапустите хост:

```json
{"mcp": {"taskmatic": {"type": "local", "command": ["python3", "<installed-skill-path>/scripts/taskmatic.py", "mcp"], "enabled": true}}}
```

Проверьте `taskmatic_list` и `taskmatic_read`, затем вызывайте `taskmatic_claim` перед
работой агента. MCP и CLI используют общую базу. Не редактируйте `taskmatic.db` и
производные Markdown-зеркала; исправляйте карточки командами. Не добавляйте базу,
заметки и экспорты в Git. Ошибка отсутствующей базы означает, что выбран другой каталог
или ещё не создана первая карточка, а не необходимость создать базу веб-сервером.
