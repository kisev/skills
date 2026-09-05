---
name: multi-run
description: Запустить и сравнить 2-5 изолированных attempts одной задачи с подтверждённым fusion.
license: MIT
compatibility: Requires OpenCode 1.18.29+ and agent-skills-opencode; Python 3.12+ stdlib-only runner.
metadata:
  author: "Kirill Sevriugin"
  version: "1.0.0"
---

# Multi-run

Runner владеет только group records, receipts и terminal manifests в user-owned
XDG state. Execution, sessions, worktrees и routing остаются package tools. Без
явно настроенных `AGENT_SKILLS_ROUTE_API` и `AGENT_SKILLS_ATTEMPTS_API` mutation
не происходит: runner возвращает `escalate`.

```text
multi_run.py preview --task-file FILE --project PATH --start-ref REF --count 2..5
multi_run.py apply --confirmation-id ID --confirmation-digest SHA256
multi_run.py status|compare --multi-run-id ID
multi_run.py fusion-preview --multi-run-id ID --source-run-ids ID[,ID] --strengths TEXT
multi_run.py fusion-apply --confirmation-id ID --confirmation-digest SHA256
```

Каждый run обязан иметь уникальные attempt/session/workspace identifiers. До
terminal status transcript, reasoning, output и diff не принимаются. Fusion
создаёт новую попытку и никогда не копирует или не сливает worktree источников.
