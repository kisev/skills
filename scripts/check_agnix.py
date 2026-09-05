#!/usr/bin/env python3
"""Enforce agnix errors and reject warnings outside the recorded baseline."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / ".agnix-warnings.json"


def fingerprint(diagnostic: dict[str, Any]) -> str:
    return "\t".join(str(diagnostic.get(key, "")) for key in ("rule", "file", "line", "message"))


def main() -> int:
    result = subprocess.run(
        [
            "agnix",
            "--config",
            ".agnix.toml",
            "--format",
            "json",
            "validate",
            "skills",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="")
    try:
        report = json.loads(result.stdout)
        baseline = set(json.loads(BASELINE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError) as error:
        print(f"agnix baseline check failed: {error}", file=sys.stderr)
        return 2

    diagnostics = report.get("diagnostics", [])
    warnings = [item for item in diagnostics if item.get("level") == "warning"]
    errors = [item for item in diagnostics if item.get("level") == "error"]
    for item in warnings:
        print(
            f"agnix warning: {item.get('file')}:{item.get('line')} "
            f"{item.get('rule')}: {item.get('message')}",
            file=sys.stderr,
        )
    current = {fingerprint(item) for item in warnings}
    new_warnings = current - baseline
    stale_warnings = baseline - current
    if stale_warnings:
        print("agnix warning baseline is stale; remove resolved entries", file=sys.stderr)
    if new_warnings:
        print("agnix found warnings outside the baseline", file=sys.stderr)
    if errors:
        for item in errors:
            print(
                f"agnix error: {item.get('file')}:{item.get('line')} "
                f"{item.get('rule')}: {item.get('message')}",
                file=sys.stderr,
            )
    return 1 if result.returncode or errors or new_warnings or stale_warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
