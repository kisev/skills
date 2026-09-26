#!/usr/bin/env python3
"""Append-only private journal for people skills in XDG state."""

from __future__ import annotations

import argparse
import calendar
import errno
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..state_artifacts import (
        ensure_private_directory,
        inspect_private_directory,
        xdg_state_home,
    )
else:
    _state_path = Path(__file__).with_name("state_artifacts.py")
    if not _state_path.exists():
        _state_path = next(
            parent / "state_artifacts.py"
            for parent in Path(__file__).resolve().parents
            if (parent / "state_artifacts.py").is_file()
        )
    _state_spec = importlib.util.spec_from_file_location("state_artifacts", _state_path)
    if _state_spec is None or _state_spec.loader is None:
        raise ImportError("state runtime is unavailable") from None
    _state_module = importlib.util.module_from_spec(_state_spec)
    _state_spec.loader.exec_module(_state_module)
    ensure_private_directory = _state_module.ensure_private_directory
    inspect_private_directory = _state_module.inspect_private_directory
    xdg_state_home = _state_module.xdg_state_home

SCHEMA_VERSION = 1
ENTRY_TYPES = frozenset({"1on1", "agreement", "fact", "note", "feedback"})
RESOLUTIONS = frozenset({"fulfilled", "broken"})
TEXT_MAX = 4000
PERSON_MAX = 200
SOURCE_MAX = 2048
MAX_ENTRIES = 100000
DEFAULT_LIMIT = 50


class JournalError(ValueError):
    """Expected safe journal failure."""


class JournalIOError(RuntimeError):
    """Journal I/O failure."""


def emit(value: object) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")


def fail(code: str, message: str, exit_code: int = 2) -> int:
    emit({"status": "error", "code": code, "message": message})
    return exit_code


def valid_profile_name(value: str) -> str:
    if (
        not value
        or len(value) > 63
        or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in value)
    ):
        raise JournalError("profile name is invalid")
    return value


def journal_root(profile: str, *, create: bool = True) -> Path:
    name = valid_profile_name(profile)
    home = xdg_state_home()
    path = home / "agent-skills" / "team" / name / "journal"
    if create:
        try:
            return ensure_private_directory(path, home)
        except (OSError, ValueError) as error:
            raise JournalIOError("journal directory is unsafe") from error
    if not path.exists():
        return path
    try:
        return inspect_private_directory(path, home)
    except (OSError, ValueError) as error:
        raise JournalIOError("journal directory is unsafe") from error


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sync_file(descriptor: int) -> None:
    try:
        os.fsync(descriptor)
    except OSError as exc:
        if exc.errno not in (errno.EINVAL, errno.EPERM):
            raise JournalIOError("journal writes require POSIX file fsync") from exc


def sync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            sync_file(handle.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise JournalIOError(f"journal write failed: {exc}") from exc


def private_regular(path: Path, label: str) -> Path:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise JournalError(f"{label} is unavailable") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1 << 20:
        raise JournalError(f"{label} must be a small regular non-symlink file")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise JournalError(f"{label} must not be accessible by group or other users")
    return path


def valid_text(value: object, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise JournalError(f"{label} is invalid")
    return value.strip()


def valid_optional_text(value: object, label: str, *, maximum: int) -> str | None:
    if value is None:
        return None
    return valid_text(value, label, maximum=maximum)


def valid_date(value: object, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise JournalError(f"{label} must be an ISO date")
    return value


def valid_iso_instant(value: str, label: str) -> float:
    match = re.fullmatch(
        r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})",
        value,
    )
    if match is None:
        raise JournalError(f"{label} must be a timezone-aware ISO-8601 instant")
    year, month, day, hour, minute, second = (int(match.group(i)) for i in range(1, 7))
    try:
        stamp = calendar.timegm((year, month, day, hour, minute, second, 0, 0, 0))
    except ValueError as exc:
        raise JournalError(f"{label} must be a timezone-aware ISO-8601 instant") from exc
    offset = 0.0
    if match.group(8) != "Z":
        sign = 1 if match.group(8)[0] == "+" else -1
        offset = sign * (int(match.group(8)[1:3]) * 3600 + int(match.group(8)[4:6]) * 60)
    fractional = float(match.group(7)) if match.group(7) else 0.0
    return stamp - offset + fractional


def entry_id(document: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


def document_of(root: Path, identifier: str) -> dict[str, Any]:
    path = private_regular(root / f"{identifier}.json", "journal entry")
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JournalError("journal entry is invalid") from exc
    if not isinstance(value, dict):
        raise JournalError("journal entry is invalid")
    return value


def scan_entries(root: Path) -> list[dict[str, Any]]:
    if not root.exists():
        return []
    entries: list[dict[str, Any]] = []
    count = 0
    for path in sorted(root.iterdir()):
        if path.suffix != ".json" or path.name.startswith(".") or not path.is_file():
            continue
        count += 1
        if count > MAX_ENTRIES:
            raise JournalError("journal exceeds the supported entry count")
        value = document_of(root, path.stem)
        if value.get("id") != path.stem:
            raise JournalError("journal entry id does not match its file name")
        entries.append(value)
    entries.sort(key=lambda item: (item["created_at"], item["id"]))
    return entries


def append_entry(
    profile: str,
    entry_type: str,
    person: str | None,
    text: str,
    *,
    due: str | None = None,
    source: str | None = None,
    resolves: str | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    if entry_type not in ENTRY_TYPES:
        raise JournalError("entry type is invalid")
    if resolves is not None and not re.fullmatch(r"[0-9a-f]{64}", resolves):
        raise JournalError("resolves must reference a journal entry id")
    if due is not None:
        valid_date(due, "due")
    root = journal_root(profile)
    document = {
        "schema_version": SCHEMA_VERSION,
        "type": entry_type,
        "person": person,
        "text": text,
        "due": due,
        "source": source,
        "resolves": resolves,
        "status": "open" if entry_type == "agreement" else None,
        "created_at": now if now is not None else time.time(),
    }
    if resolves is not None:
        target = document_of(root, resolves)
        if target.get("type") != "agreement" or target.get("status") != "open":
            raise JournalError("only an open agreement can be resolved")
        document["status"] = None
    identifier = entry_id(document)
    document["id"] = identifier
    path = root / f"{identifier}.json"
    if path.exists():
        private_regular(path, "journal entry")
        return {"status": "ok", "id": identifier, "duplicate": True, "entry": document}
    atomic_write(path, canonical_bytes(document))
    return {"status": "ok", "id": identifier, "duplicate": False, "entry": document}


def resolved_ids(entries: list[dict[str, Any]]) -> set[str]:
    resolved: set[str] = set()
    for value in entries:
        target = value.get("resolves")
        if isinstance(target, str):
            resolved.add(target)
    return resolved


def list_entries(
    profile: str,
    *,
    person: str | None = None,
    entry_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
    only_open: bool = False,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    root = journal_root(profile, create=False)
    entries = scan_entries(root)
    resolved = resolved_ids(entries)
    since_stamp = valid_iso_instant(since, "--since") if since else None
    until_stamp = valid_iso_instant(until, "--until") if until else None
    filtered: list[dict[str, Any]] = []
    for value in entries:
        if person is not None and value.get("person") != person:
            continue
        if entry_type is not None and value.get("type") != entry_type:
            continue
        if since_stamp is not None and value["created_at"] < since_stamp:
            continue
        if until_stamp is not None and value["created_at"] >= until_stamp:
            continue
        if only_open and value.get("status") != "open":
            continue
        if only_open and value["id"] in resolved:
            continue
        filtered.append(value)
    limited = filtered[-limit:] if limit > 0 else filtered
    return {
        "status": "ok",
        "profile": valid_profile_name(profile),
        "total": len(filtered),
        "returned": len(limited),
        "entries": limited,
    }


def show_entry(profile: str, identifier: str) -> dict[str, Any]:
    if re.fullmatch(r"[0-9a-f]{64}", identifier) is None:
        raise JournalError("entry id is invalid")
    root = journal_root(profile, create=False)
    document = document_of(root, identifier)
    return {"status": "ok", "entry": document}


def open_agreements(profile: str, *, person: str | None = None) -> dict[str, Any]:
    root = journal_root(profile, create=False)
    entries = scan_entries(root)
    resolved = resolved_ids(entries)
    agreements = [
        value
        for value in entries
        if value.get("type") == "agreement"
        and value.get("status") == "open"
        and value["id"] not in resolved
    ]
    if person is not None:
        agreements = [value for value in agreements if value.get("person") == person]
    return {"status": "ok", "profile": valid_profile_name(profile), "open": agreements}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capabilities", action="store_true")
    commands = parser.add_subparsers(dest="command")
    append = commands.add_parser("journal-append")
    append.add_argument("--profile", required=True)
    append.add_argument("--type", required=True)
    append.add_argument("--person")
    append.add_argument("--text", required=True)
    append.add_argument("--due")
    append.add_argument("--source")
    append.add_argument("--resolves")
    listing = commands.add_parser("journal-list")
    listing.add_argument("--profile", required=True)
    listing.add_argument("--person")
    listing.add_argument("--type")
    listing.add_argument("--since")
    listing.add_argument("--until")
    listing.add_argument("--open", action="store_true")
    listing.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    show = commands.add_parser("journal-show")
    show.add_argument("--profile", required=True)
    show.add_argument("--id", required=True)
    open_list = commands.add_parser("journal-open")
    open_list.add_argument("--profile", required=True)
    open_list.add_argument("--person")
    return parser


def run_command(arguments: argparse.Namespace) -> int:
    if arguments.capabilities:
        emit(
            {
                "schema_version": 1,
                "payload_version": "1.0.0",
                "mutation": "private-state-append",
                "dry_run": False,
                "state_protocol": "append-only-entry-store",
                "store_location": (
                    "${XDG_STATE_HOME:-$HOME/.local/state}/agent-skills/team/<profile>/journal/"
                ),
                "entry_types": sorted(ENTRY_TYPES),
                "destructive_flags": [],
                "external_mutations": False,
            }
        )
        return 0
    if arguments.command == "journal-append":
        person = valid_optional_text(arguments.person, "--person", maximum=PERSON_MAX)
        source = valid_optional_text(arguments.source, "--source", maximum=SOURCE_MAX)
        emit(
            append_entry(
                arguments.profile,
                arguments.type,
                person,
                valid_text(arguments.text, "--text", maximum=TEXT_MAX),
                due=arguments.due,
                source=source,
                resolves=arguments.resolves,
            )
        )
        return 0
    if arguments.command == "journal-list":
        if arguments.type is not None and arguments.type not in ENTRY_TYPES:
            raise JournalError("--type is invalid")
        if arguments.limit < 0 or arguments.limit > MAX_ENTRIES:
            raise JournalError("--limit is invalid")
        emit(
            list_entries(
                arguments.profile,
                person=valid_optional_text(arguments.person, "--person", maximum=PERSON_MAX),
                entry_type=arguments.type,
                since=arguments.since,
                until=arguments.until,
                only_open=arguments.open,
                limit=arguments.limit,
            )
        )
        return 0
    if arguments.command == "journal-show":
        emit(show_entry(arguments.profile, arguments.id))
        return 0
    if arguments.command == "journal-open":
        emit(
            open_agreements(
                arguments.profile,
                person=valid_optional_text(arguments.person, "--person", maximum=PERSON_MAX),
            )
        )
        return 0
    raise JournalError("a supported subcommand is required")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        arguments = parser.parse_args(argv)
        return run_command(arguments)
    except JournalError as exc:
        return fail("invalid_input", str(exc))
    except JournalIOError as exc:
        return fail("io_error", str(exc), exit_code=4)
    except OSError as exc:
        return fail("io_error", f"local I/O failed: {exc}", exit_code=4)


if __name__ == "__main__":
    raise SystemExit(main())
