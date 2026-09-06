---
name: goal
description: Управлять проверяемой целью, привязанной к OpenCode session, когда нужен ограниченный и аудируемый автономный цикл.
license: MIT
compatibility: Requires OpenCode 1.18.29+ and @kisev/skills-opencode; Python 3.12+ stdlib-only runner.
allowed-tools: native Question
metadata:
  author: "Kirill Sevriugin"
  version: "1.1.1"
---

# Goal

Прочитай `references/work-item-contract.md`. Перед `start` goal должен иметь
валидный normalized work item (`work-item/v1`), а completion должен быть связан с
каждым acceptance criterion и его evidence. Проверка machine rules выполняется
через `scripts/work_item.py validate`; feasibility и смысловые противоречия
передаются как structured semantic assessment. Invalid item не запускается.

Runner хранит только user-owned state в XDG state directory OpenCode. Он требует
явный session ID либо `OPENCODE_SESSION_ID`, не меняет permissions и не запускает
loop. Loop доступен только через явно включённый package plugin.

```text
python3 -I -S -B scripts/goal.py prepare --session ID --objective TEXT
python3 -I -S -B scripts/goal.py list [--project PATH]
python3 -I -S -B scripts/goal.py show --goal-id ID
python3 -I -S -B scripts/goal.py start|pause --goal-id ID --revision N [--session ID]
python3 -I -S -B scripts/goal.py remove --goal-id ID --revision N --dry-run
```

`prepare` создаёт paused goal. `start` и `pause` проверяют revision и session
binding. Plugin учитывает turn/token limits, сохраняет audit receipts и переводит
цель только в `paused`, `complete` или `blocked` по наблюдаемому событию.
Удаление всегда двухфазное: preview выдаёт одноразовый digest, apply повторно
проверяет digest, expiry и revision.

Старое persisted state читается совместимо: прежние поля, receipts и revisions
сохраняются, а отсутствующий work item восстанавливается через versioned legacy
adapter при чтении. GitLab artifacts не являются частью goal state и не удаляются.

Для сложной цели или явного запроса один независимый premortem проход выполняется
до старта. Он может вернуть не более трёх причин провала; основной агент отдельно
принимает или отклоняет каждую. При отсутствии независимого агента результат
`skipped`, self-review не имитируется и запуск не блокируется.
