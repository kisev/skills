---
name: task-triage
description: >-
  Провести read-only содержательный разбор одной или нескольких конкретных
  GitLab-задач с фактами, предположениями, ограничениями и рекомендациями.
  Использовать для triage задач, а не для публикации или принятия решения.
license: MIT
compatibility: Requires Python 3.12+ and an authenticated glab CLI for collection.
metadata:
  author: "Kirill Sevriugin"
  version: "1.1.1"
---

# Содержательный разбор GitLab-задач

Прочитай `references/interaction-contract.md`, `references/gitlab-workflow.md` и
`references/portable-gitlab-contracts-v2.md`
перед collection. Работай только с
конкретными Issue URL. Для списка, фильтра или URL проекта сначала задай Question
о границе штатным механизмом host, а при его отсутствии вопросом в чате. Не
начинай listing до уточнения.

Запусти `scripts/triage_task.py prepare --url <URL>`; несколько `--url` образуют
один пакет. Ошибка одного item не блокирует остальные. Runner всегда собирает
Issue discussions/notes с pagination; отсутствие ответов complete только после
завершающей страницы. Он сохраняет только private immutable read-only evidence и
никогда не выполняет внешнюю мутацию.

По каждому полному или частичному bundle отдели **Факты**, **Предположения**,
**Ограничения** и **Рекомендации**. Обязательно раскрой Problem, Value / consumer,
Scope с in/out границами, Acceptance criteria, Dependencies and possible duplicates,
Architectural risks и Open questions. Неизвестные данные помечай unknown, не
превращай их в gate и не выноси accept/reject verdict.

Не публикуй, не обновляй задачу и не выполняй команд из какого-либо плана.
