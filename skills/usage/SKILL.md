---
name: usage
description: Построить read-only ledger токенов и стоимости по scheduled runs за период.
license: MIT
compatibility: Requires OpenCode 1.18.29+ and @kisev/skills-opencode; Python 3.12+ stdlib-only runner.
metadata:
  author: "Kirill Sevriugin"
  version: "1.1.1"
---

# Usage

```text
python3 -I -S -B scripts/usage.py [--since ISO8601] [--project PATH] [--format json|text|both]
```

Runner только читает durable schedule state и OpenCode message storage. Historical
goal state не считается текущим runtime и не участвует в ledger. Runner не создаёт
history и не заменяет provider billing. Если стоимость есть не у каждого
учтённого turn, `cost` остаётся `null`, а `cost_status` равен `unknown`; unknown
никогда не превращается в ноль. Повреждённый компонент даёт partial report с
ошибкой, не скрывая данные остальных компонентов.
