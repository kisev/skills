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


PYPROJECT_LINE = re.compile(r'(?m)^([ \t]*)version = "[^"]*"$')
INIT_LINE = re.compile(r'(?m)^([ \t]*)__version__ = "[^"]*"$')


def stamp(version: str, pyproject: Path = PYPROJECT, package_init: Path = INIT) -> None:
    """Rewrite both skillmate version fields in the (ephemeral) working tree.

    TOML formatters indent table keys, so the matched line's indentation is
    preserved in the replacement.
    """
    if not PRERELEASE.fullmatch(version):
        raise ValueError("version must be a PEP 440 prerelease")
    targets = (
        (pyproject, PYPROJECT_LINE, 'version = "{}"'),
        (package_init, INIT_LINE, '__version__ = "{}"'),
    )
    for path, pattern, template in targets:
        text = path.read_text(encoding="utf-8")
        match = pattern.search(text)
        if match is None:
            raise ValueError(f"{path.name} has no skillmate version line to stamp")
        line = match.group(1) + template.format(version)
        _write(path, text[: match.start()] + line + text[match.end() :])


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
