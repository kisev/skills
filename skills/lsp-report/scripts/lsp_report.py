#!/usr/bin/env python3
"""Report OpenCode LSP applicability without starting a language server."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

scripts = Path(__file__).resolve().parent
if str(scripts) not in sys.path:
    sys.path.insert(0, str(scripts))

from portable_runtime.capabilities import emit_capabilities
from portable_runtime.contract import ContractArgumentParser, report_error
from portable_runtime.lsp import detect


def parser() -> argparse.ArgumentParser:
    result = ContractArgumentParser(prog="lsp-report")
    result.add_argument("--capabilities", action="store_true", help=argparse.SUPPRESS)
    result.add_argument("--project", default=".")
    result.add_argument("--format", choices=("json", "text"), default="json")
    return result


def text(report: dict[str, object]) -> str:
    rows = [f"{report['project']}: OpenCode LSP 1.18.29+"]
    for server in report["servers"]:  # type: ignore[index]
        item = server  # type: ignore[assignment]
        rows.append(f"{item['name']}: {item['reason']}; install: {item['install']}")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    if emit_capabilities(argv, cli, payload_version="1.0.0", mutation="read", supports_dry_run=False):
        return 0
    args = cli.parse_args(argv)
    report = detect(Path(args.project))
    if report["status"] == "error":
        report_error("invalid_project", str(report["error"]))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True) if args.format == "json" else text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
