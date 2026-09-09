# LSP Report

The report is host-neutral and read-only. For every catalog entry show four
independent states: `applicability` (`applicable` or `not-applicable`),
`configuration` (`enabled`, `disabled`, or `unknown`), `binary` (`available`,
`missing`, or `unknown`), and `runtime` (`active`, `inactive`, or `unknown`).
Only confirmed host adapters may provide a non-unknown state. Without a host API
return `unknown`; never start or install a language server.

Run `python3 -I -S -B scripts/lsp_report.py` with an optional project and JSON or
text format. Do not request diagnostics or invoke a package manager.
