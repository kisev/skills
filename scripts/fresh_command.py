#!/usr/bin/env python3
"""Run a command once per input state under an exclusive lock.

Parallel gate jobs share the root node_modules tree and the workspace dist
directories; concurrent cold invocations of npm ci or the workspace builds
wipe those trees while sibling jobs read them. The wrapper hashes the
declared inputs, skips the command while the recorded stamp matches, and
serializes cold runs with an advisory lock so the second invocation finds
the fresh state and skips instead of rebuilding under readers.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FreshCommandError(Exception):
    """The wrapped command or the input state cannot be established."""


def input_files(inputs: list[str]) -> list[Path]:
    """Resolve every declared input to a sorted list of concrete files."""
    files: set[Path] = set()
    for pattern in inputs:
        matches = sorted(ROOT.glob(pattern))
        if not matches:
            raise FreshCommandError(f"input pattern matched nothing: {pattern}")
        for match in matches:
            if match.is_dir():
                files.update(path for path in match.rglob("*") if path.is_file())
            else:
                files.add(match)
    if not files:
        raise FreshCommandError("the declared inputs resolved to no files")
    return sorted(files)


def input_digest(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--stamp", type=Path, required=True)
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        dest="inputs",
        help="glob or directory rooted at the repository (repeatable)",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER, help="command after --")
    arguments = parser.parse_args(argv)
    if not arguments.inputs:
        parser.error("at least one --input is required")
    command = arguments.command[1:] if arguments.command[:1] == ["--"] else arguments.command
    if not command:
        parser.error("a command is required")
    lock = ROOT / arguments.lock if not arguments.lock.is_absolute() else arguments.lock
    stamp = ROOT / arguments.stamp if not arguments.stamp.is_absolute() else arguments.stamp
    try:
        digest = input_digest(input_files(arguments.inputs))
    except (FreshCommandError, OSError) as error:
        print(f"fresh command failed: {error}", file=sys.stderr)
        return 1
    if stamp.is_file() and stamp.read_text(encoding="utf-8") == digest:
        print(f"fresh: {arguments.stamp} matches the declared inputs")
        return 0
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            if stamp.is_file() and stamp.read_text(encoding="utf-8") == digest:
                print(f"fresh: {arguments.stamp} matches the declared inputs")
                return 0
            completed = subprocess.run(command, cwd=ROOT, check=False)
            if completed.returncode != 0:
                return completed.returncode
            stamp.parent.mkdir(parents=True, exist_ok=True)
            temporary = stamp.with_name(f".{stamp.name}.tmp")
            temporary.write_text(digest, encoding="utf-8")
            temporary.replace(stamp)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
