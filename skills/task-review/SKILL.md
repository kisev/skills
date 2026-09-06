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

Прочитай `references/gitlab-workflow.md`. Принимай один конкретный MR либо один
или несколько конкретных Issue URL. Не анализируй код, архитектуру, безопасность
или полный исходный diff; для MR достаточно служебных данных, изменённых файлов и
статуса pipeline. Неспецифичный target требует явного подтверждения границы до API.

Запусти `scripts/review_task.py prepare --url <URL>` для каждого явного target в
одном пакете. Сохрани ошибку отдельного item в сводке и продолжи остальные.

Проверь только выбранные или все группы: `description`, `labels`, `ownership`,
`workflow`. Не угадывай исполнителя или ревьюера. Метки сверяй с полным
пагинированным списком; pipeline и конфликты остаются read-only evidence.

Сформируй один проверенный Markdown-план с дословными предлагаемыми title и
description, delta меток и непроверенным контекстом. Перед ручной публикацией
выполни `finalize`; не publish, resolve, approve, merge или push.
