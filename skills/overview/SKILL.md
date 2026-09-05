---
name: overview
description: Построить read-only сводку durable OpenCode state текущего проекта или явного project registry.
license: MIT
compatibility: Requires OpenCode 1.18.29+ and @kisev/skills-opencode; Python 3.12+ stdlib-only runner.
metadata:
  author: "Kirill Sevriugin"
  version: "1.0.0"
---

# Overview

```text
python3 -I -S -B scripts/overview.py [--project PATH] [--all] [--format json|text|both]
```

Runner читает только documented file-backed state goal, schedule, attempts и
multi-run. `--all` использует лишь явный `projects.json`, не сканирует диск.
Повреждённые, отсутствующие и unsupported records обозначаются на уровне
компонента; runner не запускает sessions, plugins, сеть или recovery.
