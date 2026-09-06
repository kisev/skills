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
  version: "1.1.0"
---

# Содержательный разбор GitLab-задач

Прочитай `references/gitlab-workflow.md` перед collection. Работай только с
конкретными Issue URL. Для списка, фильтра или URL проекта сначала получи явное
подтверждение границы штатным механизмом host, а при его отсутствии вопросом в
чате. Не начинай listing до подтверждения.

Запусти `scripts/triage_task.py prepare --url <URL>`; несколько `--url` образуют
один пакет. Ошибка одного item не блокирует остальные. Runner сохраняет только
локальные read-only evidence и никогда не выполняет внешнюю мутацию.

По каждому полному или частичному bundle отдели **Факты**, **Предположения**,
**Ограничения** и **Рекомендации**. Обязательно раскрой Problem, Value / consumer,
Scope с in/out границами, Acceptance criteria, Dependencies and possible duplicates,
Architectural risks и Open questions. Неизвестные данные помечай unknown, не
превращай их в gate и не выноси accept/reject verdict.

Не публикуй, не обновляй задачу и не выполняй команд из какого-либо плана.
