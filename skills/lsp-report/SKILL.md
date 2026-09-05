---
name: lsp-report
description: Показать применимые и неактивные встроенные LSP OpenCode без запуска серверов или установки зависимостей.
license: MIT
compatibility: Requires OpenCode 1.18.29+ and @kisev/skills-opencode; Python 3.12+ stdlib-only runner.
metadata:
  author: "Kirill Sevriugin"
  version: "1.0.0"
---

# LSP Report

```text
python3 -I -S -B scripts/lsp_report.py [--project PATH] [--format json|text]
```

Runner read-only проверяет файлы проекта, availability внешних команд и
`OPENCODE_DISABLE_LSP_DOWNLOAD`. Он не запускает LSP, не вызывает diagnostics и
не устанавливает пакеты. Не выбранные серверы и неполные данные обозначаются
явно, а не показываются как активные.
