---
name: release-review
description: >-
  Проверить один релизный GitLab MR по полноте изменений, версии, совместимости и
  готовности к выпуску. Использовать для read-only release review, а не для
  подготовки, публикации или слияния.
license: MIT
compatibility: Requires Python 3.12+ and an authenticated glab CLI for collection.
metadata:
  author: "Kirill Sevriugin"
  version: "1.0.0"
---

# Ревью релизного MR

Прочитай `references/gitlab-workflow.md`. Принимай один точный MR URL; без него
попроси ссылку. Не создавай worktree и не изменяй repository, MR, issue, release,
pipeline или другую внешнюю систему.

Проверь полноту collection, точный head SHA, версию, changelog, состав релиза,
несовместимые изменения, миграции, заметки обновления, rollback, release artifacts
и pipeline точного SHA. Сверяй существенные утверждения с diff, target branch и
связанными задачами. Сообщай только подтверждённые замечания с evidence,
последствием и минимальным исправлением.

Итог содержит verdict `ready`, `not_ready` или `blocked`, boolean readiness и gates
`semver`, `compatibility`, `migration`, `rollback`, `ci`. Каждый gate содержит
проверенный status, inputs и evidence. При неполном или изменившемся target verdict
только `blocked`. Не публикуй комментарии, одобрение, метки или статус.
