---
name: mr-prepare
description: >-
  Подготовить русские заголовок, описание и проверенный Markdown-план публикации
  обычного GitLab MR по точному diff, коммитам и статусу CI без выполнения команд.
  Использовать для не-релизного MR, а не для code review.
license: MIT
compatibility: Requires Python 3.12+ and an authenticated glab CLI for collection.
metadata:
  author: "Kirill Sevriugin"
  version: "1.1.0"
---

# Подготовка обычного MR

Прочитай `references/gitlab-workflow.md`. Принимай только один конкретный MR URL;
не создавай batch. Runner собирает metadata, changed files, pipeline для точного
head SHA и полный пагинированный список меток.

Проверь title и описание по проверяемому diff, коммитам, связанным задачам и
проектным шаблонам. В описании не выдумывай критерии, риски, тесты или связи.
Успешные проверки упоминай только при подтверждённом статусе. Явно перечисли
неполную collection и непроверенные дополнительные проверки.

Подготовь один Markdown-план с title, description, изменением меток и ownership.
Перед ручной публикацией выполни
`scripts/prepare_mr.py finalize --artifact-root <path>`: изменившийся SHA, объект
или метки блокируют план. Не создавай, не
обновляй, не approve, не merge и не push MR.
