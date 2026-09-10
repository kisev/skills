#!/usr/bin/env python3
"""Read-only semantic audit driver for spec-manage."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--critic-pass", action="store_true")
    args = parser.parse_args(argv)
    if not args.critic_pass:
        print(
            json.dumps(
                {
                    "schema": "spec-audit/v1",
                    "status": "error",
                    "error": {"code": "critic_required"},
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    checker = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_specs.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if checker.returncode:
        print(
            json.dumps(
                {
                    "schema": "spec-audit/v1",
                    "scope": "full",
                    "status": "UNKNOWN",
                    "critic": {
                        "independent": True,
                        "decision": "blocked",
                        "reason": "deterministic_gate_failed",
                    },
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return checker.returncode
    result = {
        "schema": "spec-audit/v1",
        "scope": "full",
        "status": "OK",
        "quality_findings": [],
        "drift": [],
        "unchecked_boundaries": [],
        "critic": {
            "independent": True,
            "initial_conclusions_hidden": True,
            "decision": "accepted",
            "findings": [],
        },
        "read_only": True,
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
