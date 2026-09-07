---
name: task-review
description: >-
  Проверить оформление и служебные поля конкретных GitLab-задач или MR: описание,
  связи, метки, назначения, состояние и CI. Использовать для metadata review, а не
  для глубокого анализа реализации.
license: MIT
compatibility: Requires Python 3.12+ and an authenticated glab CLI for collection.
metadata:
  author: "Kirill Sevriugin"
  version: "1.1.1"
---

# Проверка оформления GitLab

Прочитай `references/interaction-contract.md`, `references/gitlab-workflow.md`,
`references/portable-gitlab-contracts-v2.md` и
`references/work-item-contract.md`. Review начинается с validator report для
normalized item; machine и semantic findings не смешиваются. Всегда возвращай
ровно один verdict: `ready`, `needs_clarification` или `blocked`, findings с
evidence и recommended changes. Для неизменного item и evidence повторный verdict
должен быть тем же.
Принимай один конкретный MR либо один
или несколько конкретных Issue URL. Не анализируй код, архитектуру, безопасность
или полный исходный diff; для MR достаточно служебных данных, изменённых файлов и
статуса pipeline. Неспецифичный target требует Question о границе до API.

Запусти `scripts/review_task.py prepare --url <URL>` для каждого явного target в
одном пакете. Сохрани ошибку отдельного item в сводке и продолжи остальные.

Проверь только выбранные или все группы: `description`, `labels`, `ownership`,
`workflow`. Не угадывай исполнителя или ревьюера. Метки сверяй с полным
пагинированным списком; pipeline и конфликты остаются read-only evidence.

Проверка должна описывать конечное состояние, а не журнал действий. Учитывай
достижимость criteria при известных dependencies, согласованность outcome/scope и
safety. При циклической или недоступной dependency возвращай `blocked`.

Для сложной задачи или явного запроса перед review допускается ровно один
independent premortem. Он только предлагает до трёх причин провала; item не
редактирует, а основной агент принимает или отклоняет предложения с причинами.
Без независимого агента укажи `skipped` и продолжи workflow.

Сформируй один проверенный Markdown-план с дословными предлагаемыми title и
description, delta меток и непроверенным контекстом. Перед ручной публикацией
выполни `finalize`; не publish, resolve, approve, merge или push.
