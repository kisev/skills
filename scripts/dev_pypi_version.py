#!/usr/bin/env python3
"""Derive and stamp the PEP 440 dev prerelease version of skillmate."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PACKAGE = ROOT / "packages" / "skills" / "package.json"
PYPROJECT = ROOT / "apps" / "skillmate" / "pyproject.toml"
INIT = ROOT / "apps" / "skillmate" / "src" / "skillmate" / "__init__.py"
SEMVER = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
PRERELEASE = re.compile(
    r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"\.dev(?:0|[1-9][0-9]*)$"
)


def derive(base: str, run_number: str) -> str:
    """The PyPI dev prerelease: 12.0.1.dev140, unique and immutable per run.

    Shares the run number with the Pages dev version so both channels stay
    traceable to the same publication run.
    """
    if not SEMVER.fullmatch(base):
        raise ValueError("base version must be stable X.Y.Z")
    if not run_number.isdigit() or run_number.startswith("0"):
        raise ValueError("run number must be a positive integer without leading zeroes")
    version = f"{base}.dev{run_number}"
    if not PRERELEASE.fullmatch(version):
        raise ValueError("derived version is not a PEP 440 prerelease")
    return version


def _write(path: Path, text: str) -> None:
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise


def stamp(version: str, pyproject: Path = PYPROJECT, package_init: Path = INIT) -> None:
    """Rewrite both skillmate version fields in the (ephemeral) working tree."""
    if not PRERELEASE.fullmatch(version):
        raise ValueError("version must be a PEP 440 prerelease")
    targets = (
        (pyproject, re.compile(r'(?m)^version = "[^"]*"$'), f'version = "{version}"'),
        (
            package_init,
            re.compile(r'(?m)^__version__ = "[^"]*"$'),
            f'__version__ = "{version}"',
        ),
    )
    for path, pattern, line in targets:
        text = path.read_text(encoding="utf-8")
        # The validated prerelease version contains no regex escapes, so the
        # replacement string is safe to pass through subn directly.
        updated, count = pattern.subn(line, text, count=1)
        if count != 1:
            raise ValueError(f"{path.name} has no skillmate version line to stamp")
        _write(path, updated)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-number", required=True)
    parser.add_argument(
        "--stamp",
        action="store_true",
        help="rewrite the skillmate version fields before printing",
    )
    args = parser.parse_args(argv)
    try:
        package = json.loads(PACKAGE.read_text(encoding="utf-8"))
        version = derive(str(package.get("version", "")), args.run_number)
        if args.stamp:
            stamp(version)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
