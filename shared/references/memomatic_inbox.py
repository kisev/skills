#!/usr/bin/env python3
"""Presence-detected drops into the memomatic memory inbox.

Skills and agents append Markdown entry lines here; the deterministic
`memomatic process` pass (or the nightly dream sweep) validates them, applies
never-save rules, and moves accepted entries into the memory corpus. When the
inbox directory does not exist the drop is skipped silently, so portable
skills keep working on hosts without memomatic.

Entry line format (matches the memomatic corpus format):

    - text <!-- source: skill-name --> <!-- key: stable-id --> <!-- origin: agent -->

The `source` annotation is required and drives usage visibility: entries with
team-* sources, `gitlab`, or `spec-manage` may be quoted in team-facing
artifacts; every other source stays personal-only.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path
from typing import NoReturn

SOURCE_PATTERN = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
KEY_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
MAX_LINES = 16
MAX_TOTAL_BYTES = 16 * 1024
MAX_TEXT_BYTES = 2_000


class InboxError(ValueError):
    """The requested memory drop is invalid."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise InboxError(message)


def _annotations(
    source: str,
    key: str | None,
    origin: str,
    project: str | None,
    importance: int | None,
    trigger: list[str],
) -> str:
    parts: list[str] = [f"source: {source}"]
    if key:
        if not KEY_PATTERN.fullmatch(key):
            raise InboxError("key must be kebab-case")
        parts.append(f"key: {key}")
    parts.append(f"origin: {origin}")
    parts.append(f"observed: {time.strftime('%Y-%m-%d', time.gmtime())}")
    if project:
        parts.append(f"project: {project}")
    if importance is not None:
        parts.append(f"importance: {importance}")
    if trigger:
        parts.append(f"trigger: {'; '.join(trigger)}")
    return " ".join(f"<!-- {part} -->" for part in parts)


def entry_lines(
    texts: list[str],
    *,
    source: str,
    key: str | None = None,
    origin: str = "agent",
    project: str | None = None,
    importance: int | None = None,
    trigger: list[str] | None = None,
) -> list[str]:
    """Build well-formed inbox entry lines for the given texts."""
    if not SOURCE_PATTERN.fullmatch(source):
        raise InboxError("source must be kebab-case")
    if origin not in {"user", "agent"}:
        raise InboxError("origin must be user or agent")
    if not texts:
        raise InboxError("at least one text is required")
    if len(texts) > MAX_LINES:
        raise InboxError(f"at most {MAX_LINES} entries per drop")
    suffix = _annotations(source, key, origin, project, importance, trigger or [])
    lines: list[str] = []
    total = 0
    for text in texts:
        value = " ".join(str(text).split())
        if not value:
            raise InboxError("entry text must not be empty")
        encoded = value.encode()
        if len(encoded) > MAX_TEXT_BYTES:
            raise InboxError(f"entry text exceeds {MAX_TEXT_BYTES} bytes")
        line = f"- {value} {suffix}"
        total += len(line.encode())
        if total > MAX_TOTAL_BYTES:
            raise InboxError(f"drop exceeds {MAX_TOTAL_BYTES} bytes total")
        lines.append(line)
    return lines


def xdg_state_home() -> Path:
    configured = os.environ.get("XDG_STATE_HOME")
    path = Path(configured) if configured else Path.home() / ".local" / "state"
    if not path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts[1:]):
        raise InboxError("XDG_STATE_HOME must be an absolute normalized path")
    return path


def inbox_directory() -> Path:
    return xdg_state_home() / "memomatic" / "inbox"


def drop_memory(lines: list[str], source: str) -> Path | None:
    """Append one inbox drop file; return None when memomatic is absent."""
    if not lines:
        return None
    if not SOURCE_PATTERN.fullmatch(source):
        raise InboxError("source must be kebab-case")
    directory = inbox_directory()
    if directory.is_symlink() or not directory.is_dir():
        return None
    stamp = time.strftime("%Y%m%dT%H%M%S", time.gmtime())
    name = f"{source}-{stamp}-{secrets.token_hex(4)}.md"
    content = ("\n".join(lines) + "\n").encode()
    if len(content) > MAX_TOTAL_BYTES + 512:
        raise InboxError("drop is too large")
    temporary = f".{name}.{os.getpid()}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(directory / temporary, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        view = memoryview(content)
        while view:
            view = view[os.write(descriptor, view) :]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(directory / temporary, directory / name)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(directory / temporary)
        raise
    return directory / name


def run_drop(arguments: argparse.Namespace) -> int:
    lines = entry_lines(
        arguments.text,
        source=arguments.source,
        key=arguments.key,
        origin=arguments.origin,
        project=arguments.project,
        importance=arguments.importance,
        trigger=arguments.trigger,
    )
    path = drop_memory(lines, arguments.source)
    print(
        json.dumps(
            {"status": "dropped" if path else "skipped", "path": str(path) if path else None}
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = Parser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    drop = commands.add_parser("drop")
    drop.add_argument("--source", required=True)
    drop.add_argument("--text", action="append", required=True)
    drop.add_argument("--key")
    drop.add_argument("--origin", choices=["user", "agent"], default="agent")
    drop.add_argument("--project")
    drop.add_argument("--importance", type=int)
    drop.add_argument("--trigger", help="comma- or semicolon-separated trigger phrases")
    try:
        arguments = parser.parse_args(argv)
        if arguments.command == "drop":
            if arguments.trigger:
                arguments.trigger = [
                    item.strip() for item in re.split(r"[;,]", arguments.trigger) if item.strip()
                ]
            else:
                arguments.trigger = []
            return run_drop(arguments)
        raise InboxError("unsupported command")
    except InboxError as error:
        print(json.dumps({"status": "error", "error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
