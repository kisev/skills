```text
python3 -I -S -B scripts/lsp_report.py [--project PATH] [--format json|text]
```

The read-only runner checks project files, availability of external commands, and `OPENCODE_DISABLE_LSP_DOWNLOAD`. It uses materialized `lsp-catalog.json`, does not start LSPs, request diagnostics, or install packages. OpenCode host runtime status is unavailable to the portable runner and is reported as `unavailable`; unselected servers and incomplete data must not be reported as active.

# LSP Report

```text
python3 -I -S -B scripts/lsp_report.py [--project PATH] [--format json|text]
```

The read-only runner checks project files, availability of external commands, and `OPENCODE_DISABLE_LSP_DOWNLOAD`. It uses the materialized `lsp-catalog.json`, does not start an LSP, invoke diagnostics, or install packages. The OpenCode host runtime status is unavailable to the portable runner and is marked `unavailable`; unselected servers and incomplete data are not presented as active.
