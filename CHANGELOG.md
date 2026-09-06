# История изменений

Все заметные изменения проекта фиксируются в этом файле. Формат основан на
[Keep a Changelog](https://keepachangelog.com/ru/1.1.0/) и проект использует
[Semantic Versioning](https://semver.org/lang/ru/).

## [1.1.0] - 2026-09-06

### Добавлено

- Прямой CLI для inventory и настройки models/variants fixed agents, явного
  reconcile и безопасного добавления или удаления additional critics.
- Package tool `agent_profiles` и четыре optional thin slash-команды без
  отдельного skill.
- Отдельные profile configuration и semantic deployment manifest с exact critic
  pool, rendered hashes и сохранением настроек при package update.

### Изменено

- Исправлены полные manager, critic и review contracts: fresh card/approval,
  запрет direct worker remediation и exact allowlists без prefix wildcard.
- Ownership fixed agents перенесён из generic installer в profile domain;
  commands и plugins остаются под generic ownership.
- Все installer и profile mutations используют private receipts с TTL,
  lifecycle lock, final inventory validation и journaled all-or-rollback
  transaction с recovery.

### Безопасность

- Exact-name user-owned collision блокирует apply, unknown agents не изменяются,
  а миграция `1.0.0` требует точного manifest и SHA-256 совпадения.
- State primitives запрещают symlink targets и parents, используют private modes,
  atomic writes и безопасный append.

## [1.0.0] - 2026-09-05

### Добавлено

- Первый публичный стабильный выпуск переносимых Agent Skills.
- Независимый npm package `@kisev/skills-opencode` с opt-in OpenCode installer,
  agents, commands и plugin factories.
- Документация по установке skills, подключению OpenCode, обновлению, удалению и
  security boundaries.

### Безопасность

- Write-capable skills и installer используют preview с явным подтверждением.
- OpenCode installer сохраняет ownership manifest и не перезаписывает чужие либо
  изменённые пользователем files.
- После bootstrap v1.0.0 публикация npm package выполняется из GitHub Actions
  через OIDC trusted publishing без long-lived publish token.
