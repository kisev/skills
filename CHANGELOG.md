# История изменений

Все заметные изменения проекта фиксируются в этом файле. Формат основан на
[Keep a Changelog](https://keepachangelog.com/ru/1.1.0/) и проект использует
[Semantic Versioning](https://semver.org/lang/ru/).

## [2.0.2] - 2026-09-10

### Исправлено

- CI specification-impact helper теперь корректно разрешает annotated tag push:
  tag-object из `event.after` сверяется с commit из `GITHUB_SHA`, после чего
  range строится от первого parent release commit.
- Добавлен regression test для ошибки `v2.0.0` с zero-before и failed run
  `https://github.com/kisev/skills/actions/runs/34496801895`.

### Не изменено

- Runtime, skills, public inventory и behavioral contracts не изменялись.

## [2.0.1] - 2026-09-10

### Исправлено

- CI specification-impact gate теперь детерминированно разрешает ranges для pull
  request, обычного branch push, первого branch push и tag push.
- Tag push больше не передаёт zero SHA в Git: release commit проверяется как
  достижимый из `origin/main`, а impact range строится от его первого parent.
- Некорректные, отсутствующие и недостижимые event SHAs завершают gate fail closed.

### Не изменено

- Это CI-only исправление: runtime, skills, public inventory и behavioral contracts
  не изменялись. Portable skill metadata остаётся `2.0.0`.

## [2.0.0] - 2026-09-10

### Несовместимые изменения

- Удалены skills `attempt`, `schedule`, `usage` и `overview` без replacement.
- `project-spec`, `skill-improver` и `walkthrough` переименованы в `spec-manage`,
  `skill-improve` и `code-explain` соответственно.
- `team-workflow` заменён пятью fixed skills: `team-sprint-start`,
  `team-sprint-close`, `team-retro`, `team-roadmap` и `slides-prompts-prepare`.
- Удалены старые skill/command/plugin surfaces, включая slash-команду `/route`;
  package tool `route` остаётся доступен без slash-команды.
- Action и mode aliases удалены: публичная поверхность использует только точные
  имена из catalog.

### Установка и миграция

- Portable skills устанавливаются напрямую из GitHub tag с pinned executable
  (для Codex замените `opencode` на `codex`):

  ```shell
  npx --yes skills@1.5.23 add https://github.com/kisev/skills/tree/v2.0.0 \
    --agent opencode --skill '*' --copy --yes
  ```

- Exact migration с `v1.2.0` использует migration inventory и сохраняет
  ownership/hash evidence; renamed skills требуют ручной проверки нового имени.
- Reconcile переводит retired exact-owned assets в private content-addressed
  archive со статусом `archive-pending`; modified, user-owned и unknown assets
  остаются conflicts. Archive, restore и purge в этот выпуск не входят.

### OpenCode

- `@kisev/skills-opencode@2.0.0` совместим с OpenCode `>=1.18.29 <1.19.0` и
  требует Node.js 22+.
- Portable skills и optional OpenCode integration устанавливаются независимо;
  integration не включает skills и не изменяет `opencode.json`.

### Известные ограничения

- Mattermost ещё не имеет полной parity с заявленными сценариями.
- Runtime state и `doctor` требуют дополнительного hardening.
- Stateful plugins остаются opt-in, scheduler и связанные wrappers
  disabled-by-default; `ast-grep` и `rtk` требуют заранее установленные CLI.
- Live evaluation не входит в обычный quality gate и запускается только явно в
  доверенном окружении.

## [1.2.0] - 2026-09-07

### Добавлено

- Единый versioned `work-item/v1` contract для `askme`, `task-prepare`,
  `task-review` и `goal` с canonical schema, materialized validator и
  deterministic structured reports.
- Optional independent premortem для сложных work items с явными решениями
  основного агента.

### Изменено

- `goal` стал read-only portable формирователем `work-item/v1`; lifecycle и
  auto-continuation удалены. Historical state оставлен для будущей классификации.

## [1.1.1] - 2026-09-06

### Изменено

- Installer CLI по умолчанию показывает короткий человекочитаемый plan и таблицу
  agent inventory; полный стабильный JSON доступен только с `--json`.
- Preview печатает готовую confirm-команду и сворачивает длинные группы paths, не
  скрывая conflicts, digest, TTL и restart flag.

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
