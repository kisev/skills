# Инвентарь миграции

[English](../migration-inventory.md)

Этап нацелен на `2.0.0` от source ref
`5f09d504758b0e99ad9c0306df796411fbcf0f4a`. Публичная поверхность точная, без
aliases.

## Активные skills

Активны ровно 29 skills: `agents-md`, `askme`, `ast-grep`, `code-explain`,
`code-review`, `commit-msg`, `docs-prepare`, `docs-review`, `doit`, `goal`,
`humanize`, `lsp-report`, `mattermost`, `mr-prepare`, `release-prepare`,
`release-review`, `rtk`, `skill-improve`, `slides-prompts-prepare`, `spec-manage`,
`stopit`, `summary`, `task-prepare`, `task-review`, `task-triage`, `team-retro`,
`team-roadmap`, `team-sprint-close`, `team-sprint-start`.

## Миграция путей

`skills/project-spec` переименован в `skills/spec-manage`,
`skills/skill-improver` в `skills/skill-improve`, а `skills/walkthrough` в
`skills/code-explain`. Точные SHA-256 этой записи находятся
в English inventory и в machine-readable inventory.

Удалены без replacement: `skills/attempt`, `skills/schedule`, `skills/usage`,
`skills/overview`. `skills/team-workflow` разделён на `team-sprint-start`,
`team-sprint-close`, `team-retro`, `team-roadmap` и `slides-prompts-prepare`;
каждый skill имеет fixed entrypoint без public mode selector.

## Команды и безопасность

Registry содержит ровно 33 команды: 29 одноимённых skill commands и
`/capabilities`, `/doctor`, `/reconcile`, `/agent-profiles`. Package tool
`route` сохранён без slash-command. Aliases отсутствуют.

Новые retired assets получают статус `archive-pending`: reconcile сохраняет их
bytes, а apply блокирует необратимое удаление до archive lifecycle. Archive,
restore и purge не входят в этот этап.

Machine inventory: `packages/opencode/assets/migration-inventory.json` и
`shared/manifest.json`.
