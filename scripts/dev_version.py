#!/usr/bin/env python3
"""Derive one unique development version without choosing a stable SemVer."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages" / "opencode" / "package.json"
SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
REVISION = re.compile(r"^[0-9a-f]{40}$")


def derive(base: str, run_number: str, revision: str) -> str:
    if not SEMVER.fullmatch(base):
        raise ValueError("base version must be stable X.Y.Z")
    if not run_number.isdigit() or run_number.startswith("0"):
        raise ValueError("run number must be a positive integer without leading zeroes")
    if not REVISION.fullmatch(revision):
        raise ValueError("revision must be a full lowercase Git SHA")
    return f"{base}-dev.{run_number}.g{revision[:12]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-number", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args(argv)
    try:
        package = json.loads(PACKAGE.read_text(encoding="utf-8"))
        version = derive(str(package.get("version", "")), args.run_number, args.revision)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
