---
name: team-workflow
description: >-
  Выполнить одно явно выбранное действие командного цикла: planning, sprint-status,
  sprint-close, retro, roadmap или slides-prompts. Использовать только с явно
  переданным context без организационных defaults и автоматического discovery.
license: MIT
compatibility: Requires Python 3.12+.
metadata:
  author: "Kirill Sevriugin"
  version: "1.0.0"
---

# Командный workflow

Прими ровно один action: `planning`, `sprint-status`, `sprint-close`, `retro`,
`roadmap` или `slides-prompts`. Не объединяй actions и не выводи проекты,
участников, cadence или delivery signals из repository activity. Нужен ровно один
явный context: read-only JSON-файл, сохранённый именованный context или факты чата.

Сначала запусти `scripts/team_workflow.py action-check` с одним источником. Если
обязательных полей не хватает, верни `setup-required`, покажи найденные значения и
спроси только missing fields через механизм host или в чате. Общая предварительная
настройка, неявные defaults и автоматическое discovery запрещены.

Период всегда задавай как `[since, until)`. Для `planning` подготовь только scope;
`sprint-status` не закрывает цикл; `sprint-close` не выполняет planning; `retro`
не меняет roadmap; `roadmap` не создаёт презентацию; `slides-prompts` не меняет
presentation или изображения. Не выдавай `merged`, `tagged` и `shipped` за одно
состояние.

Запись context, roadmap, presentation или prompts проходит два шага:
`context-prepare` либо `artifact-prepare` показывает точный preview и confirmation
id, затем после явного подтверждения `context-save` либо `artifact-apply` повторно
проверяет digest, срок, одноразовость и путь. Workspace context file не изменяй.
Symlink, traversal и stale confirmation отклоняй. Внешняя публикация не входит в
этот skill.
