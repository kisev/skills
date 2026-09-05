---
name: goal
description: Управлять проверяемой целью, привязанной к OpenCode session, когда нужен ограниченный и аудируемый автономный цикл.
license: MIT
compatibility: Requires OpenCode 1.18.29+ and @kisev/skills-opencode; Python 3.12+ stdlib-only runner.
allowed-tools: native Question
metadata:
  author: "Kirill Sevriugin"
  version: "1.0.0"
---

# Goal

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
