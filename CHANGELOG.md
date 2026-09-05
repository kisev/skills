# История изменений

Все заметные изменения проекта фиксируются в этом файле. Формат основан на
[Keep a Changelog](https://keepachangelog.com/ru/1.1.0/) и проект использует
[Semantic Versioning](https://semver.org/lang/ru/).

## [1.0.0] - 2026-09-05

### Добавлено

- Первый публичный стабильный выпуск переносимых Agent Skills.
- Независимый npm package `agent-skills-opencode` с opt-in OpenCode installer,
  agents, commands и plugin factories.
- Документация по установке skills, подключению OpenCode, обновлению, удалению и
  security boundaries.

### Безопасность

- Write-capable skills и installer используют preview с явным подтверждением.
- OpenCode installer сохраняет ownership manifest и не перезаписывает чужие либо
  изменённые пользователем files.
- Публикация npm package выполняется из GitHub Actions через OIDC trusted
  publishing без long-lived publish token.
