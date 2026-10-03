#!/usr/bin/env python3
"""Current-session skill diagnosis runner used by the skill-doctor workflow."""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import re
import secrets
import sqlite3
import stat
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast
from urllib.parse import quote

_scripts = Path(__file__).resolve().parent


def _load_portable_runtime() -> None:
    """Make the shared portable runtime importable from authored or built layouts."""
    scripts = Path(__file__).resolve().parent
    if (scripts / "portable_runtime" / "capabilities.py").is_file():
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        return
    runtime = next(
        (
            parent / "shared" / "references" / "python_runtime"
            for parent in scripts.parents
            if (parent / "shared" / "references" / "python_runtime" / "capabilities.py").is_file()
        ),
        None,
    )
    if runtime is None:
        raise ImportError("portable runtime is unavailable") from None
    if "portable_runtime" in sys.modules:
        return
    package_spec = importlib.util.spec_from_file_location(
        "portable_runtime",
        runtime / "__init__.py",
        submodule_search_locations=[str(runtime)],
    )
    if package_spec is None or package_spec.loader is None:
        raise ImportError("portable runtime is unavailable") from None
    package = importlib.util.module_from_spec(package_spec)
    sys.modules["portable_runtime"] = package
    package_spec.loader.exec_module(package)
    for name in ("capabilities", "contract"):
        spec = importlib.util.spec_from_file_location(
            f"portable_runtime.{name}", runtime / f"{name}.py"
        )
        if spec is None or spec.loader is None:
            raise ImportError("portable runtime is unavailable") from None
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"portable_runtime.{name}"] = module
        spec.loader.exec_module(module)


if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable, Iterator

    from shared.references.python_runtime.capabilities import emit_capabilities
    from shared.references.python_runtime.contract import ContractArgumentParser, report_error
    from shared.references.state_artifacts import (
        StateArtifactError,
        archive_json,
        canonical_json,
        content_digest,
        open_state_directory,
        xdg_state_home,
    )
else:
    import importlib.util

    _load_portable_runtime()
    from portable_runtime.capabilities import emit_capabilities
    from portable_runtime.contract import ContractArgumentParser, report_error

    _state_path = _scripts / "state_artifacts.py"
    if not _state_path.exists():
        _state_path = next(
            parent / "shared" / "references" / "state_artifacts.py"
            for parent in _scripts.parents
            if (parent / "shared" / "references" / "state_artifacts.py").is_file()
        )
    _state_spec = importlib.util.spec_from_file_location("state_artifacts", _state_path)
    if _state_spec is None or _state_spec.loader is None:
        raise ImportError("state_artifacts runtime is unavailable") from None
    _state_module = importlib.util.module_from_spec(_state_spec)
    _state_spec.loader.exec_module(_state_module)
    archive_json = _state_module.archive_json
    canonical_json = _state_module.canonical_json
    content_digest = _state_module.content_digest
    open_state_directory = _state_module.open_state_directory
    xdg_state_home = _state_module.xdg_state_home
    StateArtifactError = _state_module.StateArtifactError

DIAGNOSIS_SCHEMA = "agent-skills/skill-doctor/diagnosis/v1"
REPORT_REQUEST_SCHEMA = "agent-skills/skill-doctor/report-request/v1"
REPORT_MANIFEST_SCHEMA = "agent-skills/skill-doctor/report/v1"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SESSION_KEY_RE = re.compile(r"^[0-9a-f]{16}$")
EXAMPLE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
ISO_TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
SKILL_TOOL_NAME = "skill"
UNKNOWN_SKILL_NAME = "(unknown)"
COMMAND_WRAPPERS = frozenset(
    {
        "task",
        "mise",
        "uv",
        "npm",
        "pnpm",
        "yarn",
        "bun",
        "npx",
        "git",
        "docker",
        "go",
        "cargo",
        "kubectl",
        "helm",
        "gh",
        "glab",
    }
)
HOST_LABELS = ("opencode", "kilo", "mimo", "custom")


def xdg_data_home() -> Path:
    value = os.environ.get("XDG_DATA_HOME")
    return Path(value) if value else Path.home() / ".local" / "share"


def mimo_database() -> Path:
    home = os.environ.get("MIMOCODE_HOME")
    if home:
        return Path(home) / "data" / "mimocode.db"
    return xdg_data_home() / "mimocode" / "mimocode.db"


HOST_DATABASES: dict[str, Callable[[], Path]] = {
    "opencode": lambda: xdg_data_home() / "opencode" / "opencode.db",
    "kilo": lambda: xdg_data_home() / "kilo" / "kilo.db",
    "mimo": mimo_database,
}
REQUIRED_SESSION_TABLES = ("session", "message", "part")
DEFAULT_MAX_EXCERPT_CHARS = 1200
DEFAULT_MAX_ACTIONS = 2000
DEFAULT_MAX_MESSAGES = 2000
MAX_EVIDENCE_ENTRIES = 500
MAX_OBSERVATIONS = 200
MAX_EXCERPT_LENGTH = 8000
MAX_SUMMARY_LENGTH = 2000
MAX_STDIN_BYTES = 8 * 1024 * 1024
MAX_REPORT_CHARS = 200_000
MAX_EXAMPLE_FILES = 10
MAX_SOURCE_FILE_BYTES = 1_000_000
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600
PUBLIC_ARCHIVE_EPOCH = 946684800
CLASSIFICATIONS = ("skill-defect", "environment", "agent-execution")
OBSERVATION_STATUSES = ("suspected", "confirmed")
EVIDENCE_KINDS = (
    "skill-invocation",
    "skill-error",
    "user-intervention",
    "workaround",
    "outcome",
    "action",
    "observation",
)
ORIGIN_KINDS = ("declared", "local", "unknown")
REPORT_HEADING_TITLES = (
    "Identification",
    "Expected behavior",
    "Actual behavior",
    "Minimal example",
    "Workaround",
    "Recommendation",
)
REPORT_EXCLUSIONS = (
    "conversation history",
    "raw session logs",
    "project files",
    "private diagnosis records",
    "anonymization mapping",
)


class DoctorError(ValueError):
    """Expected doctor usage or state error."""


class SessionNotFound(DoctorError):
    """The requested session does not exist in the checked history."""


def state_root() -> Path:
    return xdg_state_home() / "agent-skills" / "skill-doctor"


def session_key(host: str, session_id: str) -> str:
    return content_digest(canonical_json({"host": host, "session_id": session_id}))[:16]


def session_state_path(key: str) -> Path:
    return state_root() / "sessions" / key / "diagnosis.json"


# ---------------------------------------------------------------------------
# Typed access helpers for validated JSON values
# ---------------------------------------------------------------------------


def as_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DoctorError(f"{label} must be an object")
    return cast("dict[str, object]", value)


def as_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise DoctorError(f"{label} must be an array")
    return value


def as_text(value: object, label: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DoctorError(f"{label} must be a non-empty string")
    if len(value) > maximum:
        raise DoctorError(f"{label} exceeds {maximum} characters")
    if "\x00" in value:
        raise DoctorError(f"{label} must not contain NUL characters")
    return value


def as_optional_text(value: object, label: str, *, maximum: int) -> str | None:
    if value is None:
        return None
    return as_text(value, label, maximum=maximum)


def as_text_list(value: object, label: str, *, maximum: int, limit: int) -> list[str]:
    items = as_list(value, label)
    if len(items) > limit:
        raise DoctorError(f"{label} exceeds {limit} entries")
    return [as_text(item, f"{label} entry", maximum=maximum) for item in items]


def as_object_list(value: object, label: str, *, limit: int) -> list[dict[str, object]]:
    items = as_list(value, label)
    if len(items) > limit:
        raise DoctorError(f"{label} exceeds {limit} entries")
    return [as_object(item, label) for item in items]


def require_exact_keys(value: object, expected: set[str], label: str) -> None:
    as_object(value, label)
    keys = set(as_object(value, label))
    if keys != expected:
        missing = ", ".join(sorted(expected - keys)) or "none"
        unexpected = ", ".join(sorted(keys - expected)) or "none"
        raise DoctorError(
            f"{label} keys are invalid (missing: {missing}; unexpected: {unexpected})"
        )


def as_timestamp(value: object, label: str) -> str:
    text = as_text(value, label, maximum=64)
    if not ISO_TIMESTAMP_RE.fullmatch(text):
        raise DoctorError(f"{label} must be an ISO-8601 timestamp with a UTC offset")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise DoctorError(f"{label} must be an ISO-8601 timestamp with a UTC offset") from error
    if parsed.utcoffset() is None:
        raise DoctorError(f"{label} must be an ISO-8601 timestamp with a UTC offset")
    return text


def as_identifier(value: object, label: str) -> str:
    text = as_text(value, label, maximum=64)
    if not ID_RE.fullmatch(text):
        raise DoctorError(f"{label} must match {ID_RE.pattern}")
    return text


def as_host(value: object) -> str:
    text = as_text(value, "host", maximum=32)
    if text not in HOST_LABELS:
        raise DoctorError(f"host {text!r} is not a supported session host label")
    return text


def as_absolute_path(value: object, label: str) -> str:
    text = as_text(value, label, maximum=1024)
    path = Path(text)
    if not path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts[1:]):
        raise DoctorError(f"{label} must be an absolute normalized path")
    return text


def read_stdin_json(label: str) -> dict[str, object]:
    content = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
    if len(content) > MAX_STDIN_BYTES:
        raise DoctorError(f"{label} exceeds {MAX_STDIN_BYTES} bytes")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DoctorError(f"{label} must be valid UTF-8") from error
    if "\x00" in text:
        raise DoctorError(f"{label} must not contain NUL characters")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise DoctorError(f"{label} must be one JSON value") from error
    return as_object(value, label)


# ---------------------------------------------------------------------------
# Private XDG state primitives
# ---------------------------------------------------------------------------


def read_private_file(path: Path, boundary: Path) -> bytes | None:
    try:
        directory = open_state_directory(path.parent, boundary, create=False)
    except FileNotFoundError:
        return None
    try:
        descriptor = os.open(
            path.name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory
        )
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid():
                raise DoctorError("private state file is unsafe")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                return handle.read()
        finally:
            os.close(descriptor)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise DoctorError("private state file is unsafe") from error
    finally:
        os.close(directory)


def atomic_write_private(path: Path, boundary: Path, content: bytes) -> None:
    try:
        directory = open_state_directory(path.parent, boundary, create=True)
    except OSError as error:
        raise DoctorError("failed to prepare the private state directory") from error
    temporary = f".doctor-{secrets.token_hex(16)}"
    descriptor = -1
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, PRIVATE_FILE_MODE, dir_fd=directory)
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    except OSError as error:
        raise DoctorError("failed to atomically write the private state file") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory)
        os.close(directory)


# ---------------------------------------------------------------------------
# Session evidence collection (read-only, one explicit session only)
# ---------------------------------------------------------------------------


def resolve_session_databases(host: str, explicit: str | None) -> list[tuple[str, Path]]:
    if explicit is not None:
        path = Path(explicit)
        if not path.is_file():
            raise DoctorError(f"session database not found: {explicit}")
        label = host if host in HOST_DATABASES else "custom"
        return [(label, path)]
    hosts = list(HOST_DATABASES) if host == "auto" else [host]
    found = [(name, HOST_DATABASES[name]()) for name in hosts]
    existing = [(name, path) for name, path in found if path.is_file()]
    if not existing:
        expected = ", ".join(str(path) for _name, path in found)
        raise DoctorError(f"no session database found for host {host!r}: {expected}")
    return existing


def open_database(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(path.as_posix(), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    return connection


def require_tables(connection: sqlite3.Connection, path: Path) -> None:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    present = {row["name"] for row in rows}
    missing = [table for table in REQUIRED_SESSION_TABLES if table not in present]
    if missing:
        raise DoctorError(f"session database {path} misses tables {', '.join(missing)}")


def parse_part(data: object) -> dict[str, object] | None:
    if not isinstance(data, str):
        return None
    try:
        parsed = json.loads(data)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def state_field(part: dict[str, object], key: str) -> object:
    state = part.get("state")
    if not isinstance(state, dict):
        return None
    return state.get(key)


def first_line(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    return value.strip().splitlines()[0]


def excerpt(value: str | None, limit: int) -> str | None:
    if value is None or limit <= 0 or len(value) <= limit:
        return value
    return value[:limit]


def normalize_command(command: object) -> str:
    if not isinstance(command, str) or not command.strip():
        return "bash"
    tokens = command.strip().splitlines()[0].split()
    index = 0
    while index < len(tokens) - 1 and (
        tokens[index] == "sudo" or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[index])
    ):
        index += 1
    head = tokens[index]
    if head in COMMAND_WRAPPERS and index + 1 < len(tokens):
        return f"{head} {tokens[index + 1]}"
    return head


def bash_command(part: dict[str, object]) -> str | None:
    state_input = state_field(part, "input")
    if isinstance(state_input, dict):
        command = state_input.get("command")
        if isinstance(command, str):
            return command
    return None


def action_name(part: dict[str, object]) -> str:
    tool = part.get("tool")
    if tool == "bash":
        return f"bash:{normalize_command(bash_command(part))}"
    return f"tool:{tool if isinstance(tool, str) else 'unknown'}"


def action_example(part: dict[str, object], limit: int) -> str:
    command = first_line(bash_command(part))
    if not command:
        state_input = state_field(part, "input")
        if isinstance(state_input, dict) and state_input:
            command = first_line(json.dumps(state_input, ensure_ascii=False, sort_keys=True))
    return excerpt(command, limit) or ""


def skill_call(part: dict[str, object], time_created: int, limit: int) -> dict[str, object]:
    state_input = state_field(part, "input")
    name = UNKNOWN_SKILL_NAME
    if isinstance(state_input, dict):
        value = state_input.get("name")
        if isinstance(value, str) and value:
            name = value
    error = state_field(part, "error")
    stamp = state_field(part, "time")
    duration = None
    if isinstance(stamp, dict):
        start, end = stamp.get("start"), stamp.get("end")
        if isinstance(start, int) and isinstance(end, int) and end >= start:
            duration = end - start
    status = state_field(part, "status")
    call_id = part.get("callID")
    return {
        "call_id": call_id if isinstance(call_id, str) else "",
        "name": name,
        "status": status if isinstance(status, str) else "unknown",
        "error": excerpt(error if isinstance(error, str) else None, limit),
        "input": (
            excerpt(
                json.dumps(state_input, ensure_ascii=False, sort_keys=True)
                if isinstance(state_input, dict) and state_input
                else None,
                limit,
            )
        ),
        "time_created": time_created,
        "duration_ms": duration,
    }


def collect_session(
    host: str,
    path: Path,
    session_id: str,
    max_actions: int,
    max_messages: int,
    max_excerpt_chars: int,
) -> dict[str, object]:
    connection = open_database(path)
    try:
        require_tables(connection, path)
        session_row = connection.execute(
            "SELECT id, title, directory, time_created FROM session WHERE id = ?",
            (session_id,),
        ).fetchone()
        if session_row is None:
            raise SessionNotFound(f"session {session_id!r} does not exist in {path}")
        part_rows = connection.execute(
            "SELECT message_id, time_created, id, data FROM part"
            " WHERE session_id = ? ORDER BY time_created, id",
            (session_id,),
        ).fetchall()
        message_rows = connection.execute(
            "SELECT id, data FROM message WHERE session_id = ?",
            (session_id,),
        ).fetchall()
    finally:
        connection.close()
    roles: dict[str, str] = {}
    for row in message_rows:
        parsed = parse_part(row["data"])
        role = parsed.get("role") if parsed else None
        roles[row["id"]] = role if isinstance(role, str) else "unknown"
    title = session_row["title"]
    directory = session_row["directory"]
    time_created = session_row["time_created"]
    calls: list[dict[str, object]] = []
    messages: list[dict[str, object]] = []
    actions: list[dict[str, object]] = []
    parts_total = len(part_rows)
    parts_skipped = 0
    actions_seen = 0
    messages_seen = 0
    first_activity: int | None = None
    last_activity: int | None = None
    actions_truncated = False
    messages_truncated = False
    for row in part_rows:
        parsed = parse_part(row["data"])
        if parsed is None:
            parts_skipped += 1
            continue
        stamp = row["time_created"]
        stamp_int = stamp if isinstance(stamp, int) else 0
        first_activity = stamp_int if first_activity is None else min(first_activity, stamp_int)
        last_activity = stamp_int if last_activity is None else max(last_activity, stamp_int)
        part_type = parsed.get("type")
        if part_type == "tool":
            if parsed.get("tool") == SKILL_TOOL_NAME:
                call = skill_call(parsed, stamp_int, max_excerpt_chars)
                call["ref"] = f"call-{len(calls) + 1:04d}"
                calls.append(call)
            else:
                actions_seen += 1
                if len(actions) < max_actions:
                    actions.append(
                        {
                            "ref": f"act-{len(actions) + 1:04d}",
                            "action": action_name(parsed),
                            "example": action_example(parsed, max_excerpt_chars),
                            "time_created": stamp_int,
                        }
                    )
                else:
                    actions_truncated = True
        elif part_type == "text" and roles.get(row["message_id"]) == "user":
            text = parsed.get("text")
            if isinstance(text, str) and text.strip():
                messages_seen += 1
                if len(messages) < max_messages:
                    trimmed = excerpt(text.strip(), max_excerpt_chars)
                    messages.append(
                        {
                            "ref": f"msg-{len(messages) + 1:04d}",
                            "text": trimmed,
                            "truncated": trimmed is not None and len(trimmed) < len(text.strip()),
                            "time_created": stamp_int,
                        }
                    )
                else:
                    messages_truncated = True
    notes: list[str] = []
    if parts_skipped:
        notes.append(f"{parts_skipped} of {parts_total} parts could not be parsed")
    if actions_truncated:
        notes.append(f"action timeline truncated at {max_actions} entries")
    if messages_truncated:
        notes.append(f"user message list truncated at {max_messages} entries")
    coverage = {
        "parts_total": parts_total,
        "parts_parsed": parts_total - parts_skipped,
        "parts_skipped": parts_skipped,
        "actions_seen": actions_seen,
        "actions_listed": len(actions),
        "messages_seen": messages_seen,
        "messages_listed": len(messages),
        "truncated": actions_truncated or messages_truncated,
        "complete": parts_skipped == 0 and not actions_truncated and not messages_truncated,
        "notes": notes,
    }
    return {
        "schema_version": 1,
        "command": "collect",
        "session": {
            "id": session_row["id"],
            "host": host,
            "database": str(path),
            "title": title if isinstance(title, str) else "",
            "directory": directory if isinstance(directory, str) else "",
            "time_created": time_created if isinstance(time_created, int) else 0,
            "first_activity": first_activity,
            "last_activity": last_activity,
        },
        "coverage": coverage,
        "skill_calls": calls,
        "user_messages": messages,
        "actions": actions,
    }


def collect_command(arguments: argparse.Namespace) -> int:
    if arguments.max_excerpt_chars < 0 or arguments.max_actions < 1 or arguments.max_messages < 1:
        raise DoctorError("collect bounds must be positive")
    databases = resolve_session_databases(arguments.host, arguments.db)
    checked: list[str] = []
    failure: SessionNotFound | None = None
    for host, path in databases:
        try:
            payload = collect_session(
                host,
                path,
                arguments.session_id,
                arguments.max_actions,
                arguments.max_messages,
                arguments.max_excerpt_chars,
            )
        except SessionNotFound as error:
            checked.append(f"{host}:{path}")
            failure = error
            continue
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    detail = f"; checked {', '.join(checked)}" if checked else ""
    raise failure or DoctorError(f"the requested session could not be collected{detail}")


# ---------------------------------------------------------------------------
# Diagnosis validation
# ---------------------------------------------------------------------------


def validate_origin(value: object, label: str) -> None:
    require_exact_keys(value, {"kind", "source", "root"}, f"{label} origin")
    origin = as_object(value, f"{label} origin")
    kind = origin["kind"]
    if kind not in ORIGIN_KINDS:
        raise DoctorError(f"{label} origin kind is invalid")
    if kind == "declared":
        source = as_text(origin["source"], f"{label} origin source", maximum=512)
        if not source.startswith(("http://", "https://")):
            raise DoctorError(f"{label} origin source must be an HTTP(S) URL")
        if origin["root"] is not None:
            raise DoctorError(f"{label} declared origin must not carry a root path")
    elif kind == "local":
        as_absolute_path(origin["root"], f"{label} origin root")
        if origin["source"] is not None:
            raise DoctorError(f"{label} local origin must not carry a source URL")
    elif origin["source"] is not None or origin["root"] is not None:
        raise DoctorError(f"{label} unknown origin must not carry source or root")


def validate_diagnosis(value: object) -> dict[str, object]:
    require_exact_keys(
        value,
        {
            "schema",
            "session",
            "recorded_at",
            "coverage",
            "skills",
            "evidence",
            "observations",
            "conclusions",
            "open_questions",
        },
        "diagnosis",
    )
    diagnosis = as_object(value, "diagnosis")
    if diagnosis["schema"] != DIAGNOSIS_SCHEMA:
        raise DoctorError(f"diagnosis schema must be {DIAGNOSIS_SCHEMA}")
    as_timestamp(diagnosis["recorded_at"], "recorded_at")

    session = as_object(diagnosis["session"], "diagnosis session")
    require_exact_keys(session, {"id", "host", "workspace", "title"}, "diagnosis session")
    as_text(session["id"], "session id", maximum=256)
    as_host(session["host"])
    if session["workspace"] is not None:
        as_absolute_path(session["workspace"], "session workspace")
    if session["title"] is not None:
        as_text(session["title"], "session title", maximum=512)

    coverage = as_object(diagnosis["coverage"], "diagnosis coverage")
    require_exact_keys(
        coverage,
        {"complete", "notes", "parts_scanned", "parts_skipped", "truncated"},
        "diagnosis coverage",
    )
    for key in ("complete", "truncated"):
        if not isinstance(coverage[key], bool):
            raise DoctorError(f"coverage {key} must be boolean")
    notes = as_text_list(coverage["notes"], "coverage notes", maximum=512, limit=20)
    if not coverage["complete"] and not notes:
        raise DoctorError("incomplete coverage requires explicit notes")
    for key in ("parts_scanned", "parts_skipped"):
        number = coverage[key]
        if not isinstance(number, int) or isinstance(number, bool) or number < 0:
            raise DoctorError(f"coverage {key} must be a non-negative integer")

    skill_names: set[str] = set()
    for item in as_list(diagnosis["skills"], "diagnosis skills"):
        require_exact_keys(item, {"name", "origin"}, "diagnosis skill")
        entry = as_object(item, "diagnosis skill")
        name = as_identifier(entry["name"], "diagnosis skill name")
        if name in skill_names:
            raise DoctorError(f"diagnosis skill {name!r} is duplicated")
        skill_names.add(name)
        validate_origin(entry["origin"], f"skill {name}")

    evidence_ids: set[str] = set()
    evidence = as_list(diagnosis["evidence"], "diagnosis evidence")
    if len(evidence) > MAX_EVIDENCE_ENTRIES:
        raise DoctorError(f"diagnosis evidence exceeds {MAX_EVIDENCE_ENTRIES} entries")
    for item in evidence:
        require_exact_keys(item, {"id", "kind", "excerpt", "time"}, "diagnosis evidence entry")
        entry = as_object(item, "diagnosis evidence entry")
        entry_id = as_identifier(entry["id"], "evidence id")
        if entry_id in evidence_ids:
            raise DoctorError(f"evidence id {entry_id!r} is duplicated")
        evidence_ids.add(entry_id)
        if entry["kind"] not in EVIDENCE_KINDS:
            raise DoctorError(f"evidence {entry_id} kind is invalid")
        as_text(entry["excerpt"], f"evidence {entry_id} excerpt", maximum=MAX_EXCERPT_LENGTH)
        stamp = entry["time"]
        if not isinstance(stamp, int) or isinstance(stamp, bool):
            raise DoctorError(f"evidence {entry_id} time must be an integer")

    observation_ids: set[str] = set()
    observations = as_list(diagnosis["observations"], "diagnosis observations")
    if len(observations) > MAX_OBSERVATIONS:
        raise DoctorError(f"diagnosis observations exceed {MAX_OBSERVATIONS} entries")
    for item in observations:
        require_exact_keys(
            item,
            {
                "id",
                "classification",
                "skill",
                "status",
                "summary",
                "evidence",
                "fingerprints",
                "proposal",
                "workaround",
            },
            "diagnosis observation",
        )
        entry = as_object(item, "diagnosis observation")
        observation_id = as_identifier(entry["id"], "observation id")
        if observation_id in observation_ids:
            raise DoctorError(f"observation id {observation_id!r} is duplicated")
        observation_ids.add(observation_id)
        if entry["classification"] not in CLASSIFICATIONS:
            raise DoctorError(f"observation {observation_id} classification is invalid")
        if entry["status"] not in OBSERVATION_STATUSES:
            raise DoctorError(f"observation {observation_id} status is invalid")
        skill = entry["skill"]
        if skill is not None:
            skill_name = as_identifier(skill, f"observation {observation_id} skill")
            if skill_name not in skill_names:
                raise DoctorError(
                    f"observation {observation_id} cites undeclared skill {skill_name!r}"
                )
        as_text(
            entry["summary"], f"observation {observation_id} summary", maximum=MAX_SUMMARY_LENGTH
        )
        as_text(
            entry["proposal"], f"observation {observation_id} proposal", maximum=MAX_SUMMARY_LENGTH
        )
        as_optional_text(
            entry["workaround"],
            f"observation {observation_id} workaround",
            maximum=MAX_SUMMARY_LENGTH,
        )
        cited = as_text_list(
            entry["evidence"], f"observation {observation_id} evidence", maximum=64, limit=64
        )
        if not cited:
            raise DoctorError(f"observation {observation_id} must cite evidence")
        for reference in cited:
            if reference not in evidence_ids:
                raise DoctorError(
                    f"observation {observation_id} cites undefined evidence {reference!r}"
                )
        fingerprints = as_text_list(
            entry["fingerprints"],
            f"observation {observation_id} fingerprints",
            maximum=512,
            limit=20,
        )
        if entry["classification"] == "skill-defect" and not fingerprints:
            raise DoctorError(
                f"observation {observation_id} is a skill defect without code fingerprints"
            )

    as_text_list(diagnosis["conclusions"], "conclusions", maximum=MAX_SUMMARY_LENGTH, limit=50)
    as_text_list(
        diagnosis["open_questions"], "open questions", maximum=MAX_SUMMARY_LENGTH, limit=50
    )
    return diagnosis


def load_stored_diagnosis(path: Path, boundary: Path) -> tuple[dict[str, object], bytes] | None:
    body = read_private_file(path, boundary)
    if body is None:
        return None
    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DoctorError("stored diagnosis is not valid JSON") from error
    return validate_diagnosis(value), body


def evidence_fingerprints(diagnosis: dict[str, object]) -> dict[str, bytes]:
    return {
        str(entry["id"]): canonical_json(entry)
        for entry in as_object_list(
            diagnosis["evidence"], "diagnosis evidence entry", limit=MAX_EVIDENCE_ENTRIES
        )
    }


def observation_fingerprints(diagnosis: dict[str, object]) -> dict[str, bytes]:
    return {
        str(entry["id"]): canonical_json(entry)
        for entry in as_object_list(
            diagnosis["observations"], "diagnosis observation", limit=MAX_OBSERVATIONS
        )
    }


def record_command(arguments: argparse.Namespace) -> int:
    diagnosis = validate_diagnosis(read_stdin_json("diagnosis"))
    session = as_object(diagnosis["session"], "diagnosis session")
    if session["id"] != arguments.session_id:
        raise DoctorError("diagnosis session id does not match --session-id")
    if session["host"] != arguments.host:
        raise DoctorError("diagnosis session host does not match --host")
    key = session_key(str(session["host"]), str(session["id"]))
    boundary = state_root() / "sessions" / key
    path = boundary / "diagnosis.json"
    previous = load_stored_diagnosis(path, state_root())
    history: list[str] = []
    evidence_added = len(as_list(diagnosis["evidence"], "diagnosis evidence"))
    observations_total = len(as_list(diagnosis["observations"], "diagnosis observations"))
    observation_added = observations_total
    observation_revised = 0
    observation_retained = 0
    if previous is not None:
        previous_value, previous_body = previous
        previous_session = as_object(previous_value["session"], "stored diagnosis session")
        if (
            previous_session["id"] != arguments.session_id
            or previous_session["host"] != arguments.host
        ):
            raise DoctorError(
                "stored state belongs to a different session; refusing to overwrite it"
            )
        previous_evidence = evidence_fingerprints(previous_value)
        current_evidence = evidence_fingerprints(diagnosis)
        dropped = sorted(set(previous_evidence) - set(current_evidence))
        if dropped:
            raise DoctorError(
                "evidence is append-only; recorded evidence must not be dropped: "
                + ", ".join(dropped)
            )
        rewritten = sorted(
            reference
            for reference in set(previous_evidence) & set(current_evidence)
            if previous_evidence[reference] != current_evidence[reference]
        )
        if rewritten:
            raise DoctorError(
                "recorded evidence must not be rewritten in place: " + ", ".join(rewritten)
            )
        evidence_added = len(set(current_evidence) - set(previous_evidence))
        previous_observations = observation_fingerprints(previous_value)
        current_observations = observation_fingerprints(diagnosis)
        observation_added = len(set(current_observations) - set(previous_observations))
        retained = set(previous_observations) & set(current_observations)
        observation_revised = sum(
            1
            for reference in retained
            if previous_observations[reference] != current_observations[reference]
        )
        observation_retained = len(retained) - observation_revised
        try:
            snapshot = archive_json(path, previous_body, boundary)
        except (StateArtifactError, OSError) as error:
            raise DoctorError(f"failed to archive the previous diagnosis: {error}") from error
        history.append(snapshot.name)
    atomic_write_private(path, state_root(), canonical_json(diagnosis) + b"\n")
    summary = {
        "schema_version": 1,
        "status": "recorded",
        "session": {"id": arguments.session_id, "host": arguments.host, "key": key},
        "destination": str(path),
        "observations": {
            "total": observations_total,
            "added": observation_added,
            "revised": observation_revised,
            "retained": observation_retained,
        },
        "evidence": {
            "total": len(as_list(diagnosis["evidence"], "diagnosis evidence")),
            "added": evidence_added,
        },
        "history": history,
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


def show_command(arguments: argparse.Namespace) -> int:
    host = arguments.host if arguments.host in HOST_DATABASES else "custom"
    key = session_key(host, arguments.session_id)
    path = session_state_path(key)
    stored = load_stored_diagnosis(path, state_root())
    if stored is None:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "absent",
                    "session": {"id": arguments.session_id, "host": host, "key": key},
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    print(json.dumps(stored[0], ensure_ascii=False, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# Development-use matching against current sources
# ---------------------------------------------------------------------------


def parse_declared_source(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return ""
    closing = next((index for index, line in enumerate(lines[1:], 1) if line == "---"), -1)
    if closing < 0:
        return ""
    in_metadata = False
    for line in lines[1:closing]:
        if line.startswith("metadata:"):
            in_metadata = True
            continue
        if in_metadata and not line.startswith((" ", "\t")):
            in_metadata = False
        if in_metadata:
            match = re.fullmatch(r'\s+source:\s*"([^"]+)"', line)
            if match:
                return match.group(1)
    return ""


def load_skill_sources(skills_root: Path) -> dict[str, dict[str, object]]:
    if not skills_root.is_dir():
        raise DoctorError(f"skills root is not a directory: {skills_root}")
    sources: dict[str, dict[str, object]] = {}
    for skill_dir in sorted(skills_root.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("."):
            continue
        files: dict[str, str] = {}
        for path in sorted(skill_dir.rglob("*")):
            try:
                if not path.is_file() or path.is_symlink():
                    continue
                if path.stat().st_size > MAX_SOURCE_FILE_BYTES:
                    continue
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            files[path.relative_to(skill_dir).as_posix()] = text
        if not files:
            continue
        sources[skill_dir.name] = {
            "declared_source": parse_declared_source(files.get("SKILL.source.md", "")),
            "files": files,
        }
    return sources


def list_stored_diagnoses() -> Iterator[tuple[str, dict[str, object]]]:
    root = state_root()
    try:
        directory = open_state_directory(root / "sessions", root, create=False)
    except FileNotFoundError:
        return
    try:
        try:
            names = sorted(os.listdir(directory))
        except OSError as error:
            raise DoctorError("stored diagnoses are unreadable") from error
    finally:
        os.close(directory)
    for name in names:
        if not SESSION_KEY_RE.fullmatch(name):
            continue
        try:
            stored = load_stored_diagnosis(
                state_root() / "sessions" / name / "diagnosis.json", state_root()
            )
        except DoctorError:
            continue
        if stored is not None:
            yield name, stored[0]


def fingerprint_presence(fingerprints: list[str], files: dict[str, str]) -> list[dict[str, object]]:
    return [
        {
            "value": value,
            "present": any(value in text for text in files.values()),
            "files": sorted(relative for relative, text in files.items() if value in text),
        }
        for value in fingerprints
    ]


def match_observation(
    observation: dict[str, object],
    skill_records: dict[str, dict[str, object]],
    sources: dict[str, dict[str, object]],
    skills_root: Path,
) -> dict[str, object]:
    skill_name = str(observation["skill"])
    base: dict[str, object] = {"id": observation["id"], "skill": skill_name}
    record = skill_records.get(skill_name)
    if record is None:
        return {
            **base,
            "verdict": "needs-clarification",
            "reason": "the diagnosed skill did not declare its origin",
        }
    origin = as_object(record["origin"], f"skill {skill_name} origin")
    current = sources.get(skill_name)
    if current is None:
        return {
            **base,
            "verdict": "missing",
            "reason": "the skill is absent from the current sources",
        }
    if origin["kind"] == "unknown":
        return {
            **base,
            "verdict": "needs-clarification",
            "reason": "skill origin is ambiguous; a matching name alone is insufficient",
        }
    declared_source = str(current["declared_source"])
    if origin["kind"] == "declared":
        if origin["source"] != declared_source or not declared_source:
            return {
                **base,
                "verdict": "needs-clarification",
                "reason": (
                    "the declared origin differs from the current skill source; "
                    "a matching name alone is insufficient"
                ),
            }
    else:
        try:
            same_tree = Path(str(origin["root"])).resolve() == skills_root.resolve()
        except OSError:
            same_tree = False
        if not same_tree:
            return {
                **base,
                "verdict": "needs-clarification",
                "reason": (
                    "the recorded local origin is a different tree; a matching name "
                    "alone is insufficient"
                ),
            }
    fingerprints = as_text_list(
        observation["fingerprints"],
        f"observation {observation['id']} fingerprints",
        maximum=512,
        limit=20,
    )
    presence = fingerprint_presence(fingerprints, cast("dict[str, str]", current["files"]))
    present = sum(1 for item in presence if item["present"])
    if present == len(presence):
        verdict, reason = (
            "relevant",
            "every recorded fingerprint is still present in the current source",
        )
    elif present == 0:
        verdict, reason = "resolved", "no recorded fingerprint remains; the source changed"
    else:
        verdict, reason = (
            "unclear",
            "some fingerprints changed; clarify whether the problem remains",
        )
    return {**base, "verdict": verdict, "reason": reason, "fingerprints": presence}


def match_command(arguments: argparse.Namespace) -> int:
    skills_root = Path(arguments.skills_root)
    sources = load_skill_sources(skills_root)
    reports = []
    matched = 0
    for key, diagnosis in list_stored_diagnoses():
        session = as_object(diagnosis["session"], "diagnosis session")
        skill_records = {
            str(entry["name"]): entry
            for entry in as_object_list(diagnosis["skills"], "diagnosis skill", limit=1000)
        }
        observations = []
        for item in as_list(diagnosis["observations"], "diagnosis observations"):
            observation = as_object(item, "diagnosis observation")
            if observation["classification"] != "skill-defect" or observation["skill"] is None:
                continue
            observations.append(match_observation(observation, skill_records, sources, skills_root))
        matched += len(observations)
        reports.append(
            {
                "key": key,
                "session": {
                    "id": session["id"],
                    "host": session["host"],
                    "workspace": session["workspace"],
                },
                "observations": observations,
            }
        )
    print(
        json.dumps(
            {
                "schema_version": 1,
                "command": "match",
                "skills_root": str(skills_root),
                "diagnoses": reports,
                "matched_observations": matched,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


# ---------------------------------------------------------------------------
# Public bug report archive
# ---------------------------------------------------------------------------


def validate_report_envelope(value: object) -> dict[str, object]:
    require_exact_keys(
        value,
        {
            "schema",
            "skill",
            "source",
            "version",
            "reproduction",
            "created_at",
            "report_md",
            "example_files",
        },
        "report request",
    )
    envelope = as_object(value, "report request")
    if envelope["schema"] != REPORT_REQUEST_SCHEMA:
        raise DoctorError(f"report request schema must be {REPORT_REQUEST_SCHEMA}")
    skill = as_text(envelope["skill"], "report skill", maximum=64)
    if not NAME_RE.fullmatch(skill):
        raise DoctorError("report skill must be a valid skill name")
    if envelope["source"] is not None:
        source = as_text(envelope["source"], "report source", maximum=512)
        if not source.startswith(("http://", "https://")):
            raise DoctorError("report source must be an HTTP(S) URL")
    if envelope["version"] is not None:
        as_text(envelope["version"], "report version", maximum=64)
    if envelope["reproduction"] not in {"verified", "unverified"}:
        raise DoctorError("report reproduction must be 'verified' or 'unverified'")
    as_timestamp(envelope["created_at"], "report created_at")
    report_md = as_text(envelope["report_md"], "report text", maximum=MAX_REPORT_CHARS)
    for title in REPORT_HEADING_TITLES:
        if f"## {title}" not in report_md:
            raise DoctorError(f"report text misses the required section '## {title}'")
    example_files = as_object(envelope["example_files"], "report example_files")
    if not example_files:
        raise DoctorError("report example_files must not be empty")
    if len(example_files) > MAX_EXAMPLE_FILES:
        raise DoctorError(f"report example_files exceeds {MAX_EXAMPLE_FILES} files")
    for name, content in example_files.items():
        if not isinstance(name, str) or not EXAMPLE_NAME_RE.fullmatch(name):
            raise DoctorError(f"example file name {name!r} is not neutral")
        as_text(content, f"example file {name}", maximum=MAX_REPORT_CHARS)
    return envelope


def forbidden_values(arguments: argparse.Namespace) -> list[str]:
    values: list[str] = list(arguments.forbid_value or [])
    if arguments.forbid_file is not None:
        try:
            lines = Path(arguments.forbid_file).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as error:
            raise DoctorError("forbid file is unreadable") from error
        values.extend(line for line in lines if line)
    if arguments.session_id:
        values.append(arguments.session_id)
    with contextlib.suppress(StateArtifactError, OSError):
        values.append(str(state_root()))
    home = str(Path.home())
    if home not in {"", "/"}:
        values.append(home)
    return values


def enforce_redaction(rendered: dict[str, str], forbidden: list[str]) -> None:
    for index, value in enumerate(forbidden):
        if len(value) < 4:
            continue
        for name, content in rendered.items():
            if value in name:
                raise DoctorError(
                    f"private value #{index} appears in an archive file name; refusing to continue"
                )
            if value in content:
                raise DoctorError(
                    f"private value #{index} appears in the archive content; refusing to continue"
                )


def build_report_files(
    envelope: dict[str, object],
) -> tuple[str, dict[str, bytes], dict[str, object]]:
    example_files = as_object(envelope["example_files"], "report example_files")
    files: dict[str, str] = {
        "report.md": str(envelope["report_md"]),
        **{f"example/{name}": str(content) for name, content in sorted(example_files.items())},
    }
    files = {
        name: content if content.endswith("\n") else f"{content}\n"
        for name, content in files.items()
    }
    manifest = {
        "schema": REPORT_MANIFEST_SCHEMA,
        "skill": envelope["skill"],
        "source": envelope["source"],
        "version": envelope["version"],
        "version_status": "unknown" if envelope["version"] is None else "known",
        "reproduction": envelope["reproduction"],
        "created_at": envelope["created_at"],
        "files": {
            name: content_digest(content.encode()) for name, content in sorted(files.items())
        },
    }
    report_id = content_digest(canonical_json(manifest))[:16]
    return report_id, {name: content.encode() for name, content in files.items()}, manifest


def envelope_notes(envelope: dict[str, object]) -> list[str]:
    notes: list[str] = []
    if envelope["version"] is None:
        notes.append("the skill version is unknown and is explicitly marked in manifest.json")
    if envelope["reproduction"] == "unverified":
        notes.append("reproduction is unverified and is explicitly marked in manifest.json")
    if envelope["source"] is None:
        notes.append("the skill source is not declared in manifest.json")
    return notes


def read_existing_report(destination: Path, complete: dict[str, bytes]) -> bool:
    """Return True when every existing file matches; False when absent or conflicting."""
    try:
        directory = open_state_directory(destination, state_root(), create=False)
    except FileNotFoundError:
        return True
    try:
        for name, content in complete.items():
            try:
                descriptor = os.open(
                    name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory
                )
            except FileNotFoundError:
                continue
            try:
                with os.fdopen(descriptor, "rb", closefd=False) as handle:
                    if handle.read() != content:
                        return False
            finally:
                os.close(descriptor)
    except OSError as error:
        raise DoctorError("the existing report archive is unsafe") from error
    finally:
        os.close(directory)
    return True


def write_report_file(directory: int, name: str, content: bytes) -> None:
    temporary = f".report-{secrets.token_hex(16)}"
    descriptor = -1
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary, flags, PRIVATE_FILE_MODE, dir_fd=directory)
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.close(descriptor)
        descriptor = -1
        os.utime(
            temporary,
            (PUBLIC_ARCHIVE_EPOCH, PUBLIC_ARCHIVE_EPOCH),
            dir_fd=directory,
            follow_symlinks=False,
        )
        os.replace(temporary, name, src_dir_fd=directory, dst_dir_fd=directory)
        os.fsync(directory)
    except OSError as error:
        raise DoctorError("failed to write the report archive") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=directory)


def write_report(destination: Path, complete: dict[str, bytes]) -> None:
    directory = open_state_directory(destination, state_root(), create=True)
    try:
        for name, content in sorted(complete.items()):
            relative = Path(name)
            if len(relative.parts) > 1:
                subdirectory = open_state_directory(
                    destination / relative.parent, state_root(), create=True
                )
                try:
                    write_report_file(subdirectory, relative.name, content)
                finally:
                    os.close(subdirectory)
            else:
                write_report_file(directory, name, content)
    finally:
        os.close(directory)


def report_command(arguments: argparse.Namespace) -> int:
    envelope = validate_report_envelope(read_stdin_json("report request"))
    if envelope["skill"] != arguments.skill:
        raise DoctorError("report request skill does not match --skill")
    report_id, files, manifest = build_report_files(envelope)
    complete = {"manifest.json": canonical_json(manifest) + b"\n", **files}
    rendered = {name: content.decode("utf-8") for name, content in sorted(complete.items())}
    enforce_redaction(rendered, forbidden_values(arguments))
    destination = state_root() / "reports" / report_id
    preview_files = [
        {"path": name, "sha256": content_digest(complete[name]), "content": rendered[name]}
        for name in sorted(complete)
    ]
    commit = arguments.report_command == "commit"
    if commit and Path(arguments.expected_dir) != destination:
        raise DoctorError("report destination changed after confirmation; refusing to write")
    if not read_existing_report(destination, complete):
        raise DoctorError(
            "report destination already exists with different content; prepare new content"
        )
    summary: dict[str, object] = {
        "schema_version": 1,
        "status": "written" if commit else "preview",
        "destination": str(destination),
        "files": [{"path": item["path"], "sha256": item["sha256"]} for item in preview_files],
    }
    if commit:
        write_report(destination, complete)
    else:
        summary["files"] = [
            {
                "path": item["path"],
                "sha256": item["sha256"],
                "content": item["content"],
            }
            for item in preview_files
        ]
        summary["excluded"] = list(REPORT_EXCLUSIONS)
        summary["notes"] = envelope_notes(envelope)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------


def parser() -> ContractArgumentParser:
    result = ContractArgumentParser(prog="skill-doctor")
    result.add_argument("--capabilities", action="store_true")
    commands = result.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("collect")
    collect.add_argument("--session-id", required=True)
    collect.add_argument("--db", help="explicit session database path")
    collect.add_argument(
        "--host",
        choices=[*HOST_DATABASES, "auto"],
        default="auto",
        help="host profile used to locate databases without --db",
    )
    collect.add_argument("--max-actions", type=int, default=DEFAULT_MAX_ACTIONS)
    collect.add_argument("--max-messages", type=int, default=DEFAULT_MAX_MESSAGES)
    collect.add_argument("--max-excerpt-chars", type=int, default=DEFAULT_MAX_EXCERPT_CHARS)

    show = commands.add_parser("show")
    show.add_argument("--session-id", required=True)
    show.add_argument(
        "--host",
        choices=HOST_LABELS,
        required=True,
        help="host label that addresses the stored diagnosis",
    )

    record = commands.add_parser("record")
    record.add_argument("--session-id", required=True)
    record.add_argument("--host", choices=HOST_LABELS, required=True)

    match = commands.add_parser("match")
    match.add_argument("--skills-root", required=True)

    report = commands.add_parser("report")
    report_sub = report.add_subparsers(dest="report_command", required=True)
    for name in ("prepare", "commit"):
        sub = report_sub.add_parser(name)
        sub.add_argument("--skill", required=True)
        sub.add_argument("--session-id", help="session id that must not appear in the archive")
        sub.add_argument("--forbid-value", action="append", default=None)
        sub.add_argument("--forbid-file", help="file with one private value per line")
        if name == "commit":
            sub.add_argument("--expected-dir", required=True)
    return result


COMMAND_HANDLERS = {
    "collect": collect_command,
    "record": record_command,
    "show": show_command,
    "match": match_command,
    "report": report_command,
}


def main(argv: list[str] | None = None) -> int:
    arguments_parser = parser()
    if emit_capabilities(
        argv,
        arguments_parser,
        payload_version="1.1.0",
        mutation="write",
        supports_dry_run=False,
        confirmation=True,
    ):
        return 0
    arguments = arguments_parser.parse_args(argv)
    handler = COMMAND_HANDLERS.get(str(arguments.command))
    if handler is None:
        report_error("invalid_arguments", f"unsupported command {arguments.command!r}")
        return 2
    try:
        return handler(arguments)
    except (DoctorError, StateArtifactError, OSError, sqlite3.Error) as error:
        report_error(f"{arguments.command}_error", str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
