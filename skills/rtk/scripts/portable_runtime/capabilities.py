"""Read-only capabilities payload for portable skill runners."""

from __future__ import annotations

import json
import shutil
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse


def _option_strings(parser: argparse.ArgumentParser) -> set[str]:
    options = {option for action in parser._actions for option in action.option_strings}
    for action in parser._actions:
        choices = getattr(action, "choices", None)
        if isinstance(choices, dict):
            for child in choices.values():
                options.update(_option_strings(child))
    return options


def emit_capabilities(
    argv: list[str] | None,
    parser: argparse.ArgumentParser,
    *,
    payload_version: str,
    mutation: str,
    supports_dry_run: bool,
    external_tools: tuple[str, ...] = (),
    destructive_flags: tuple[str, ...] = (),
    confirmation: bool = False,
) -> bool:
    """Print capabilities without running a command or changing files."""
    values = sys.argv[1:] if argv is None else argv
    if "--capabilities" not in values:
        return False
    options = _option_strings(parser)
    dry_run_flag = "--dry-run" if "--dry-run" in options else None
    if (dry_run_flag is not None) != supports_dry_run:
        raise RuntimeError("capabilities dry-run declaration does not match parser")
    missing = set(destructive_flags) - options
    if missing:
        raise RuntimeError("capabilities destructive flags are not present in parser")
    state_protocol: dict[str, bool] = {"lease": False, "receipts": False}
    if confirmation:
        state_protocol["confirmation"] = True
    print(
        json.dumps(
            {
                "schema_version": 1,
                "payload_version": payload_version,
                "mutation": mutation,
                "supports_dry_run": supports_dry_run,
                "state_protocol": state_protocol,
                "external_tools": [
                    {"name": name, "available": shutil.which(name) is not None}
                    for name in external_tools
                ],
                "flags": {
                    "dry_run": dry_run_flag,
                    "destructive": sorted(destructive_flags),
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return True
