#!/usr/bin/env python3
"""Check that the optional RTK executable is available without installing it."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def _bootstrap() -> None:
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))


_bootstrap()

from portable_runtime.capabilities import emit_capabilities
from portable_runtime.contract import ContractArgumentParser, emit_escalation


def parser() -> ContractArgumentParser:
    result = ContractArgumentParser(prog="rtk")
    result.add_argument("--capabilities", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("check")
    return result


def main(argv: list[str] | None = None) -> int:
    arguments_parser = parser()
    if emit_capabilities(
        argv,
        arguments_parser,
        payload_version="1.0.0",
        mutation="read",
        external_tools=("rtk",),
        supports_dry_run=False,
    ):
        return 0
    arguments_parser.parse_args(argv)
    executable = shutil.which("rtk")
    if executable is None:
        emit_escalation(
            "RTK CLI is unavailable.",
            {
                "executable": "rtk",
                "action": "Install RTK using the host's normal toolchain.",
            },
        )
    print(
        json.dumps(
            {"schema_version": 1, "available": True, "executable": executable},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
