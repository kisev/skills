---
name: schedule
description: Управлять явными disabled-by-default scheduled task definitions для opt-in OpenCode scheduler.
license: MIT
compatibility: Requires OpenCode 1.18.29+ and @kisev/skills-opencode; Python 3.12+ stdlib-only runner.
metadata:
  author: "Kirill Sevriugin"
  version: "1.0.0"
---

# Schedule

Definitions находятся либо в `.agents/loops/*.md`, либо в user-owned XDG state.
Новая managed definition всегда `enabled: false`. Scheduler существует только при
явно включённом plugin и не воспроизводит пропущенные slots после restart.

```text
python3 -I -S -B scripts/schedule.py list|status [--project PATH]
python3 -I -S -B scripts/schedule.py add --id ID --name NAME --schedule 'every: 1h' \
  --agent AGENT --model MODEL --prompt TEXT
python3 -I -S -B scripts/schedule.py enable|disable|remove --id ID
```

Каждая mutating operation сначала возвращает exact preview и одноразовый
`confirmation_request`. Apply сверяет digest и revision. Runner не запускает
sessions, не создаёт timers и не меняет definition без confirmation.
