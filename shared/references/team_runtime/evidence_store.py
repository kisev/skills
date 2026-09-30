#!/usr/bin/env python3
"""Incremental evidence coverage store for team skills in private XDG state."""

from __future__ import annotations

import argparse
import errno
import fcntl
import importlib.util
import json
import os
import re
import stat
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:
    from ..state_artifacts import (
        archive_bytes,
        canonical_json,
        content_digest,
        ensure_private_directory,
        inspect_private_directory,
        read_immutable,
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
        raise ImportError("state_artifacts runtime is unavailable") from None
    _state_module = importlib.util.module_from_spec(_state_spec)
    _state_spec.loader.exec_module(_state_module)
    archive_bytes = _state_module.archive_bytes
    canonical_json = _state_module.canonical_json
    content_digest = _state_module.content_digest
    ensure_private_directory = _state_module.ensure_private_directory
    inspect_private_directory = _state_module.inspect_private_directory
    read_immutable = _state_module.read_immutable
    xdg_state_home = _state_module.xdg_state_home

SCHEMA_VERSION = 1
STABLE_AGE_SECONDS = 7 * 24 * 60 * 60
FRESH_TTL_SECONDS = 300
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_LABEL_BYTES = 512
LOCK_TIMEOUT_SECONDS = 5.0
LOCK_RETRY_SECONDS = 0.05
DATE_ONLY_LENGTH = 10
WINDOW_KINDS = frozenset({"gitlab-metrics", "mattermost"})
POINT_KINDS = frozenset({"mattermost", "file", "other"})
KINDS = WINDOW_KINDS | POINT_KINDS
PROFILE_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
SNAPSHOT_PATH = re.compile(r"history/(evidence|artifact)/([0-9a-f]{64})\.(json|md)\Z")


class EvidenceError(ValueError):
    """Expected safe evidence store failure."""


class EvidenceIOError(EvidenceError):
    """A store mutation or read failed safely."""


class ContractArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise EvidenceError(message)


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def fail(code: str, message: str, exit_code: int = 2) -> int:
    print(message, file=sys.stderr)
    emit({"status": "error", "error": {"code": code, "message": message, "retryable": False}})
    return exit_code


def parse_instant(value: str) -> datetime:
    text = value.strip()
    if not text:
        raise EvidenceError("timestamp must not be empty")
    try:
        if len(text) == DATE_ONLY_LENGTH:
            parsed_date = date.fromisoformat(text)
            return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=UTC)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceError(f"invalid ISO 8601 timestamp: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"timestamp must contain a UTC offset: {value}")
    return parsed.astimezone(UTC)


def format_instant(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def valid_profile_name(value: str) -> str:
    if not PROFILE_NAME.fullmatch(value):
        raise EvidenceError("profile name is invalid")
    return value


def valid_source_key(value: str) -> str:
    if not value or len(value.encode()) > 256 or not value.isprintable() or value != value.strip():
        raise EvidenceError("source key is invalid")
    return value


def valid_location(value: str) -> str:
    if not value.isprintable() or len(value.encode()) > 2048:
        raise EvidenceError("source location is invalid")
    return value


def store_root(profile: str, *, create: bool = True) -> Path:
    name = valid_profile_name(profile)
    home = xdg_state_home()
    path = home / "agent-skills" / "team" / name / "evidence"
    if create:
        try:
            return ensure_private_directory(path, home)
        except (OSError, ValueError) as error:
            raise EvidenceIOError("evidence store directory is unsafe") from error
    if not path.exists():
        return path
    try:
        return inspect_private_directory(path, home)
    except (OSError, ValueError) as error:
        raise EvidenceIOError("evidence store directory is unsafe") from error


def legacy_store_root(profile: str) -> Path:
    return xdg_state_home() / "agent-skills" / "team-evidence" / valid_profile_name(profile)


def resolve_store(profile: str) -> Path:
    current = store_root(profile, create=False)
    if current.exists():
        return current
    legacy = legacy_store_root(profile)
    if legacy.exists():
        inspect_private_directory(legacy, xdg_state_home())
        return legacy
    return current


def migrate_store(profile: str) -> dict[str, Any]:
    name = valid_profile_name(profile)
    legacy = legacy_store_root(profile)
    current = store_root(profile, create=False)
    if current.exists():
        raise EvidenceError("evidence store already exists in the current location")
    if not legacy.exists():
        raise EvidenceError("legacy evidence store is missing")
    inspect_private_directory(legacy, xdg_state_home())
    current.parent.mkdir(parents=True, exist_ok=True)
    ensure_private_directory(current.parent.parent, xdg_state_home())
    try:
        inspect_private_directory(current.parent, current.parent.parent)
    except (OSError, ValueError) as error:
        raise EvidenceIOError("evidence store parent directory is unsafe") from error
    os.rename(legacy, current)
    sync_directory(legacy.parent)
    return {"profile": name, "migrated_from": str(legacy), "migrated_to": str(current)}


def active_store(profile: str, *, create: bool = False) -> Path:
    root = resolve_store(profile)
    if create and not root.exists():
        root = store_root(profile)
    return root


def empty_manifest(profile: str) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "profile": profile, "sources": {}, "artifacts": []}


def _validate_record(value: object, key: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "collected_at",
        "complete",
        "snapshot",
        "window",
    }:
        raise EvidenceError(f"evidence record for {key!r} has invalid fields")
    window = value["window"]
    if not isinstance(window, dict) or not window:
        raise EvidenceError(f"evidence record window for {key!r} is invalid")
    if set(window) == {"since", "until"}:
        since = parse_instant(window["since"]) if isinstance(window["since"], str) else None
        until = parse_instant(window["until"]) if isinstance(window["until"], str) else None
        if since is None or until is None or since >= until:
            raise EvidenceError(f"evidence record window for {key!r} is invalid")
    elif set(window) == {"at"}:
        if not isinstance(window["at"], str):
            raise EvidenceError(f"evidence record window for {key!r} is invalid")
        parse_instant(window["at"])
    else:
        raise EvidenceError(f"evidence record window for {key!r} is invalid")
    if not isinstance(value["complete"], bool):
        raise EvidenceError(f"evidence record completeness for {key!r} is invalid")
    if not isinstance(value["collected_at"], str):
        raise EvidenceError(f"evidence record collection time for {key!r} is invalid")
    parse_instant(value["collected_at"])
    snapshot = value["snapshot"]
    if snapshot is not None and (
        not isinstance(snapshot, str) or SNAPSHOT_PATH.fullmatch(snapshot) is None
    ):
        raise EvidenceError(f"evidence record snapshot for {key!r} is invalid")
    return value


def _validate_source(value: object, key: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"kind", "label", "location", "records"}:
        raise EvidenceError(f"evidence source {key!r} has invalid fields")
    if value["kind"] not in KINDS:
        raise EvidenceError(f"evidence source {key!r} has an invalid kind")
    if not isinstance(value["location"], str):
        raise EvidenceError(f"evidence source {key!r} has an invalid location")
    label = value["label"]
    if not isinstance(label, str) or not label.isprintable() or len(label.encode()) > 512:
        raise EvidenceError(f"evidence source {key!r} has an invalid label")
    if not isinstance(value["records"], list):
        raise EvidenceError(f"evidence source {key!r} has invalid records")
    for record in value["records"]:
        _validate_record(record, key)
    return value


def validate_manifest(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError("evidence manifest must be an object")
    expected = {"schema_version", "profile", "sources", "artifacts"}
    if set(value) != expected:
        raise EvidenceError("evidence manifest has invalid fields")
    if value["schema_version"] != SCHEMA_VERSION or isinstance(value["schema_version"], bool):
        raise EvidenceError("evidence manifest schema_version is unsupported")
    valid_profile_name(str(value["profile"]))
    if not isinstance(value["sources"], dict):
        raise EvidenceError("evidence manifest sources are invalid")
    for key, source in value["sources"].items():
        valid_source_key(str(key))
        _validate_source(source, str(key))
        if source["kind"] == "gitlab-metrics" and any(
            set(record["window"]) != {"since", "until"} for record in source["records"]
        ):
            raise EvidenceError(f"evidence source {key!r} requires window records")
    if not isinstance(value["artifacts"], list):
        raise EvidenceError("evidence manifest artifacts are invalid")
    for artifact in value["artifacts"]:
        if not isinstance(artifact, dict) or set(artifact) != {
            "digest",
            "period",
            "recorded_at",
            "sources",
            "suffix",
            "target",
        }:
            raise EvidenceError("evidence artifact entry has invalid fields")
        if not isinstance(artifact["target"], str) or not Path(artifact["target"]).is_absolute():
            raise EvidenceError("evidence artifact target is invalid")
        if (
            SNAPSHOT_PATH.fullmatch(f"history/artifact/{artifact['digest']}{artifact['suffix']}")
            is None
        ):
            raise EvidenceError("evidence artifact digest or suffix is invalid")
        if not isinstance(artifact["recorded_at"], str):
            raise EvidenceError("evidence artifact timestamp is invalid")
        parse_instant(artifact["recorded_at"])
        period = artifact["period"]
        if period is not None:
            if not isinstance(period, dict) or set(period) != {"since", "until"}:
                raise EvidenceError("evidence artifact period is invalid")
            parse_instant(period["since"])
            parse_instant(period["until"])
        if not isinstance(artifact["sources"], list) or not all(
            isinstance(item, str) and valid_source_key(item) for item in artifact["sources"]
        ):
            raise EvidenceError("evidence artifact sources are invalid")
    return value


def manifest_path(root: Path) -> Path:
    return root / "manifest.json"


def load_manifest(root: Path) -> dict[str, Any]:
    path = manifest_path(root)
    try:
        raw = read_immutable(path, xdg_state_home())
    except FileNotFoundError:
        return empty_manifest(root.name)
    except (OSError, ValueError) as error:
        raise EvidenceIOError(f"evidence manifest is unreadable: {error}") from error
    if len(raw) > MAX_MANIFEST_BYTES:
        raise EvidenceError("evidence manifest exceeds the size limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError("evidence manifest is not valid JSON") from exc
    return validate_manifest(value)


def sync_file(descriptor: int) -> None:
    try:
        os.fsync(descriptor)
    except (AttributeError, NotImplementedError, OSError) as exc:
        raise EvidenceIOError("evidence writes require POSIX file fsync") from exc


def sync_directory(path: Path) -> None:
    flags = getattr(os, "O_DIRECTORY", 0)
    if os.name != "posix" or not flags:
        raise EvidenceIOError("evidence writes require POSIX directory fsync")
    try:
        descriptor = os.open(path, os.O_RDONLY | flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except (AttributeError, NotImplementedError, OSError) as exc:
        raise EvidenceIOError("evidence writes require POSIX directory fsync") from exc


def write_manifest(root: Path, manifest: dict[str, Any]) -> None:
    validate_manifest(manifest)
    rendered = canonical_json(manifest) + b"\n"
    if len(rendered) > MAX_MANIFEST_BYTES:
        raise EvidenceError("evidence manifest exceeds the size limit")
    path = manifest_path(root)
    temporary = path.with_name(f".manifest.{os.getpid()}.{time.monotonic_ns()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(rendered)
            handle.flush()
            sync_file(handle.fileno())
        os.replace(temporary, path)
        sync_directory(root)
    finally:
        temporary.unlink(missing_ok=True)


def acquire_lock(root: Path) -> int:
    if os.name != "posix" or not callable(getattr(fcntl, "flock", None)):
        raise EvidenceIOError("evidence mutations require POSIX flock locking")
    descriptor = -1
    try:
        descriptor = os.open(
            root / ".evidence.lock",
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or (hasattr(os, "geteuid") and metadata.st_uid != os.geteuid())
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise EvidenceIOError("evidence mutation lock is unsafe")
        os.fchmod(descriptor, 0o600)
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise EvidenceIOError("timed out waiting for the evidence lock") from exc
                time.sleep(min(LOCK_RETRY_SECONDS, remaining))
            else:
                return descriptor
    except EvidenceIOError:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        raise EvidenceIOError("failed to acquire the evidence lock") from exc


def merge_spans(spans: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    ordered = sorted(spans)
    merged: list[tuple[datetime, datetime]] = []
    for since, until in ordered:
        if merged and since <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], until))
        else:
            merged.append((since, until))
    return merged


def subtract_spans(
    requested: tuple[datetime, datetime], covered: list[tuple[datetime, datetime]]
) -> list[tuple[datetime, datetime]]:
    missing: list[tuple[datetime, datetime]] = []
    cursor = requested[0]
    for since, until in merge_spans(covered):
        if until <= cursor:
            continue
        if since >= requested[1]:
            break
        if since > cursor:
            missing.append((cursor, min(since, requested[1])))
        cursor = max(cursor, until)
        if cursor >= requested[1]:
            break
    if cursor < requested[1]:
        missing.append((cursor, requested[1]))
    return missing


def record_reusable(
    record: dict[str, Any], kind: str, now: datetime
) -> tuple[datetime, datetime] | None:
    window = record["window"]
    if set(window) != {"since", "until"} or not record["complete"] or record["snapshot"] is None:
        return None
    since = parse_instant(window["since"])
    until = parse_instant(window["until"])
    if kind == "gitlab-metrics":
        # Terminal delivery timestamps (merged_at, closed_at, released_at, tag
        # creation) never move, so one complete window stays reusable forever.
        return since, until
    collected_at = parse_instant(record["collected_at"])
    fresh = now - collected_at <= timedelta(seconds=FRESH_TTL_SECONDS)
    stable = now - until >= timedelta(seconds=STABLE_AGE_SECONDS)
    if not (fresh or stable):
        return None
    return since, until


def _snapshot_covers_sources(
    profile: str, record: dict[str, Any], required: frozenset[str] | set[str]
) -> bool:
    try:
        raw = read_snapshot(profile, str(record["snapshot"]))
        document = json.loads(raw.decode("utf-8"))
    except (EvidenceError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    sources = document.get("sources") if isinstance(document, dict) else None
    return isinstance(sources, dict) and required.issubset(sources)


def plan_windows(
    profile: str,
    source_key: str,
    since: datetime,
    until: datetime,
    *,
    required_sources: frozenset[str] | set[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if since >= until:
        raise EvidenceError("--since must be earlier than --until")
    current = now or datetime.now(UTC)
    root = active_store(profile)
    manifest = load_manifest(root)
    source = manifest["sources"].get(source_key)
    reusable: list[tuple[datetime, datetime]] = []
    if source is not None:
        for record in source["records"]:
            span = record_reusable(record, str(source["kind"]), current)
            if span is None or span[1] <= since or span[0] >= until:
                continue
            if required_sources is not None and not _snapshot_covers_sources(
                profile, record, required_sources
            ):
                continue
            reusable.append((max(span[0], since), min(span[1], until)))
    covered = merge_spans(reusable)
    missing = subtract_spans((since, until), covered)
    return {
        "status": "ok",
        "profile": manifest["profile"],
        "source": source_key,
        "kind": str(source["kind"]) if source is not None else None,
        "requested": {"since": format_instant(since), "until": format_instant(until)},
        "reusable_windows": [
            {"since": format_instant(item[0]), "until": format_instant(item[1])} for item in covered
        ],
        "missing_windows": [
            {"since": format_instant(item[0]), "until": format_instant(item[1])} for item in missing
        ],
        "complete": not missing,
        "external_mutations": False,
    }


def store_snapshot(root: Path, stem: str, suffix: str, content: bytes) -> tuple[str, str]:
    path = archive_bytes(root, stem, suffix, content)
    return str(path.relative_to(root)), content_digest(content)


def read_snapshot(profile: str, relative: str) -> bytes:
    if SNAPSHOT_PATH.fullmatch(relative) is None:
        raise EvidenceError("snapshot path is invalid")
    root = active_store(profile)
    home = xdg_state_home()
    if not relative.startswith("history/evidence/"):
        raise EvidenceError("snapshot path is invalid")
    try:
        return read_immutable(root / relative, home)
    except FileNotFoundError as error:
        raise EvidenceError("evidence snapshot is missing") from error
    except (OSError, ValueError) as error:
        raise EvidenceIOError(f"evidence snapshot is unreadable: {error}") from error


def record_coverage(
    profile: str,
    source_key: str,
    kind: str,
    location: str,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
    at: datetime | None = None,
    complete: bool,
    evidence: bytes | None = None,
    label: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    if kind not in KINDS:
        raise EvidenceError("source kind is invalid")
    valid_source_key(source_key)
    valid_location(location)
    if label and (not label.isprintable() or len(label.encode()) > MAX_LABEL_BYTES):
        raise EvidenceError("source label is invalid")
    if kind == "gitlab-metrics":
        if since is None or until is None or since >= until:
            raise EvidenceError("gitlab-metrics sources require a valid window")
        window: dict[str, str] = {"since": format_instant(since), "until": format_instant(until)}
    elif at is not None:
        if since is not None or until is not None:
            raise EvidenceError("a point read cannot also declare a window")
        window = {"at": format_instant(at)}
    elif since is not None and until is not None:
        if since >= until:
            raise EvidenceError("window records require since < until")
        window = {"since": format_instant(since), "until": format_instant(until)}
    else:
        raise EvidenceError("a record requires a window or a point timestamp")
    current = now or datetime.now(UTC)
    root = active_store(profile, create=True)
    descriptor = acquire_lock(root)
    try:
        manifest = load_manifest(root)
        source = manifest["sources"].get(source_key)
        if source is None:
            manifest["sources"][source_key] = {
                "kind": kind,
                "location": location,
                "label": label,
                "records": [],
            }
            source = manifest["sources"][source_key]
        if source["kind"] != kind or source["location"] != location:
            raise EvidenceError("source kind or location conflicts with the stored source")
        if label:
            source["label"] = label
        snapshot_relative: str | None = None
        if complete and evidence is not None:
            snapshot_relative, _ = store_snapshot(root, "evidence", ".json", evidence)
        record = {
            "window": window,
            "complete": complete,
            "collected_at": format_instant(current),
            "snapshot": snapshot_relative,
        }
        source["records"].append(record)
        write_manifest(root, manifest)
    finally:
        os.close(descriptor)
    return {
        "status": "recorded",
        "profile": manifest["profile"],
        "source": source_key,
        "record": record,
        "snapshot": snapshot_relative,
        "external_mutations": False,
    }


def _iter_window_records(source: dict[str, Any]) -> list[tuple[datetime, datetime, dict[str, Any]]]:
    result = []
    for record in source["records"]:
        window = record["window"]
        if set(window) == {"since", "until"}:
            result.append((parse_instant(window["since"]), parse_instant(window["until"]), record))
    return result


def show_manifest(
    profile: str,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict[str, Any]:
    if (since is None) != (until is None):
        raise EvidenceError("a provenance window requires both --since and --until")
    window: tuple[datetime, datetime] | None = None
    if since is not None and until is not None:
        if since >= until:
            raise EvidenceError("--since must be earlier than --until")
        window = (since, until)
    root = active_store(profile)
    manifest = load_manifest(root)
    sources = []
    for key in sorted(manifest["sources"]):
        source = manifest["sources"][key]
        records = source["records"]
        if window is not None:
            records = [record for record in records if _record_overlaps(record, window)]
        windows = []
        points = []
        for record in records:
            if set(record["window"]) == {"since", "until"}:
                windows.append(
                    {
                        "since": record["window"]["since"],
                        "until": record["window"]["until"],
                        "complete": record["complete"],
                        "collected_at": record["collected_at"],
                        "snapshot": record["snapshot"] is not None,
                    }
                )
            else:
                points.append(
                    {
                        "at": record["window"]["at"],
                        "complete": record["complete"],
                        "collected_at": record["collected_at"],
                        "snapshot": record["snapshot"] is not None,
                    }
                )
        coverage = None
        if window is not None and windows:
            covered = [
                (parse_instant(item["since"]), parse_instant(item["until"]))
                for item in windows
                if item["complete"]
            ]
            coverage = "complete" if not subtract_spans(window, covered) else "partial"
        sources.append(
            {
                "key": key,
                "kind": source["kind"],
                "location": source["location"],
                "label": source["label"],
                "windows": sorted(windows, key=lambda item: (item["since"], item["until"])),
                "points": sorted(points, key=lambda item: item["at"]),
                "window_coverage": coverage,
            }
        )
    if window is not None:
        sources = [item for item in sources if item["windows"] or item["points"]]
    return {
        "status": "ok",
        "profile": manifest["profile"],
        "window": (
            None
            if window is None
            else {"since": format_instant(window[0]), "until": format_instant(window[1])}
        ),
        "sources": sources,
        "artifacts": manifest["artifacts"],
        "store_path": str(root),
        "external_mutations": False,
    }


def _record_overlaps(record: dict[str, Any], window: tuple[datetime, datetime]) -> bool:
    span = record["window"]
    if set(span) == {"since", "until"}:
        record_since = parse_instant(span["since"])
        record_until = parse_instant(span["until"])
        return record_since < window[1] and record_until > window[0]
    collected_at = parse_instant(record["collected_at"])
    return window[0] <= collected_at < window[1]


def materialize_gitlab(
    profile: str,
    source_key: str,
    since: datetime,
    until: datetime,
    *,
    sources: frozenset[str] | set[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if since >= until:
        raise EvidenceError("--since must be earlier than --until")
    current = now or datetime.now(UTC)
    root = active_store(profile)
    manifest = load_manifest(root)
    source = manifest["sources"].get(source_key)
    if source is None or source["kind"] != "gitlab-metrics":
        raise EvidenceError("source is not a stored gitlab-metrics source")
    usable: list[tuple[datetime, datetime, dict[str, Any]]] = []
    reusable_spans: list[tuple[datetime, datetime]] = []
    for record_since, record_until, record in _iter_window_records(source):
        span = record_reusable(record, str(source["kind"]), current)
        if span is None or span[1] <= since or span[0] >= until:
            continue
        if sources is not None and not _snapshot_covers_sources(profile, record, sources):
            continue
        raw = read_snapshot(profile, str(record["snapshot"]))
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvidenceError("evidence snapshot is not valid JSON") from exc
        usable.append((record_since, record_until, document))
        reusable_spans.append(span)
    missing = subtract_spans((since, until), merge_spans(reusable_spans))
    items: dict[tuple[str, str, str], dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    project_name: str | None = None
    hostname: str | None = None
    project_id: str | None = None
    for _, _, document in usable:
        if not isinstance(document, dict) or set(document) != {
            "hostname",
            "period",
            "project",
            "schema_version",
            "sources",
        }:
            raise EvidenceError("evidence snapshot has an unsupported shape")
        document_hostname = str(document["hostname"])
        project = document["project"]
        if not isinstance(project, dict) or set(project) != {"project_id", "project_name"}:
            raise EvidenceError("evidence snapshot project is invalid")
        document_project_id = str(project["project_id"])
        if hostname is None:
            hostname = document_hostname
            project_id = document_project_id
            project_name = project["project_name"]
        elif hostname != document_hostname or project_id != document_project_id:
            raise EvidenceError("evidence snapshots disagree on hostname or project")
        for source_name, source_result in document["sources"].items():
            if sources is not None and source_name not in sources:
                continue
            if not isinstance(source_result, dict):
                raise EvidenceError("evidence snapshot source result is invalid")
            for item in source_result.get("items", []):
                if not isinstance(item, dict) or "event_at" not in item:
                    raise EvidenceError("evidence snapshot item is invalid")
                event_at = parse_instant(str(item["event_at"]))
                if not since <= event_at < until:
                    continue
                key = _item_identity(item)
                identity = (str(project["project_id"]), str(source_name), key)
                if identity not in items:
                    items[identity] = item
    if missing:
        errors.append(
            {
                "kind": "coverage_gap",
                "message": "stored coverage does not span the requested period",
                "windows": [
                    {"since": format_instant(item[0]), "until": format_instant(item[1])}
                    for item in missing
                ],
            }
        )
    source_names: set[str] = set()
    for _, _, document in usable:
        for source_name in document["sources"]:
            if sources is None or source_name in sources:
                source_names.add(str(source_name))
    source_results: dict[str, Any] = {
        name: {"complete": not missing, "errors": [], "count": 0, "items": []}
        for name in sorted(source_names)
    }
    for (_project_id, source_name, _key), item in items.items():
        result = source_results[source_name]
        result["items"].append(item)
        result["count"] += 1
    for result in source_results.values():
        result["items"] = sorted(
            result["items"], key=lambda value: parse_instant(str(value["event_at"]))
        )
    return {
        "schema_version": 1,
        "hostname": hostname,
        "period": {
            "since": format_instant(since),
            "until": format_instant(until),
            "semantics": "[since, until)",
        },
        "project": {"project_id": project_id, "project_name": project_name},
        "complete": not missing,
        "errors": errors,
        "sources": source_results,
    }


def _item_identity(item: dict[str, Any]) -> str:
    for field in ("id", "iid", "tag_name", "name"):
        value = item.get(field)
        if value is not None:
            return str(value)
    raise EvidenceError("evidence snapshot item lacks a stable identity")


def regular_file(path: Path, label: str) -> Path:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise EvidenceError(f"{label} is unavailable") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise EvidenceError(f"{label} must be a regular file")
    return path


def record_artifact(
    profile: str,
    target: Path,
    *,
    input_path: Path | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    sources: list[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    if not target.is_absolute():
        raise EvidenceError("artifact target must be an absolute path")
    window: tuple[datetime, datetime] | None = None
    if since is not None and until is not None:
        if since >= until:
            raise EvidenceError("artifact period requires since < until")
        window = (since, until)
    elif (since is None) != (until is None):
        raise EvidenceError("an artifact period requires both boundaries")
    suffix = target.suffix.lower()
    if suffix not in {".md", ".json"}:
        raise EvidenceError("artifact target suffix is unsupported")
    source = regular_file(input_path or target, "artifact input")
    content = source.read_bytes()
    current = now or datetime.now(UTC)
    root = active_store(profile, create=True)
    descriptor = acquire_lock(root)
    try:
        manifest = load_manifest(root)
        known = set(manifest["sources"])
        for key in sources:
            valid_source_key(key)
            if key not in known:
                raise EvidenceError(f"artifact references unknown source {key!r}")
        relative, digest_value = store_snapshot(root, "artifact", suffix, content)
        entry = {
            "target": str(target),
            "digest": digest_value,
            "suffix": suffix,
            "recorded_at": format_instant(current),
            "period": (
                None
                if window is None
                else {"since": format_instant(window[0]), "until": format_instant(window[1])}
            ),
            "sources": sorted(set(sources)),
        }
        if entry not in manifest["artifacts"]:
            manifest["artifacts"].append(entry)
        write_manifest(root, manifest)
    finally:
        os.close(descriptor)
    return {
        "status": "recorded",
        "profile": manifest["profile"],
        "artifact": entry,
        "snapshot": relative,
        "external_mutations": False,
    }


def build_parser() -> ContractArgumentParser:
    parser = ContractArgumentParser(description=__doc__)
    parser.add_argument("--capabilities", action="store_true")
    commands = parser.add_subparsers(dest="command", parser_class=ContractArgumentParser)
    plan = commands.add_parser("evidence-plan")
    plan.add_argument("--profile", required=True)
    plan.add_argument("--source", required=True)
    plan.add_argument("--since", required=True)
    plan.add_argument("--until", required=True)
    record = commands.add_parser("evidence-record")
    record.add_argument("--profile", required=True)
    record.add_argument("--source", required=True)
    record.add_argument("--kind", required=True, choices=sorted(KINDS))
    record.add_argument("--location", required=True)
    record.add_argument("--label", default="")
    record.add_argument("--since")
    record.add_argument("--until")
    record.add_argument("--at")
    record.add_argument("--incomplete", action="store_true")
    record.add_argument("--evidence")
    show = commands.add_parser("evidence-show")
    show.add_argument("--profile", required=True)
    show.add_argument("--since")
    show.add_argument("--until")
    materialize = commands.add_parser("evidence-materialize")
    materialize.add_argument("--profile", required=True)
    materialize.add_argument("--source", required=True)
    materialize.add_argument("--since", required=True)
    materialize.add_argument("--until", required=True)
    artifact = commands.add_parser("artifact-record")
    artifact.add_argument("--profile", required=True)
    artifact.add_argument("--target", required=True)
    artifact.add_argument("--input")
    artifact.add_argument("--since")
    artifact.add_argument("--until")
    artifact.add_argument("--source", action="append", default=[])
    migrate = commands.add_parser("evidence-migrate")
    migrate.add_argument("--profile", required=True)
    return parser


def run_command(arguments: argparse.Namespace) -> int:
    if arguments.capabilities:
        emit(
            {
                "schema_version": 1,
                "payload_version": "1.1.0",
                "mutation": "private-state-append",
                "dry_run": False,
                "state_protocol": "profile-scoped-coverage-manifest",
                "store_location": (
                    "${XDG_STATE_HOME:-$HOME/.local/state}/agent-skills/team/<profile>/evidence"
                ),
                "legacy_store_location": (
                    "${XDG_STATE_HOME:-$HOME/.local/state}/agent-skills/team-evidence/<profile>"
                ),
                "fresh_ttl_seconds": FRESH_TTL_SECONDS,
                "stable_age_seconds": STABLE_AGE_SECONDS,
                "destructive_flags": ["evidence-migrate"],
                "external_mutations": False,
            }
        )
        return 0
    return dispatch_command(arguments)


def dispatch_command(arguments: argparse.Namespace) -> int:
    if arguments.command == "evidence-migrate":
        emit(migrate_store(arguments.profile))
        return 0
    if arguments.command == "evidence-plan":
        emit(
            plan_windows(
                arguments.profile,
                arguments.source,
                parse_instant(arguments.since),
                parse_instant(arguments.until),
            )
        )
        return 0
    if arguments.command == "evidence-record":
        emit(record_command(arguments))
        return 0
    if arguments.command == "evidence-show":
        emit(
            show_manifest(
                arguments.profile,
                since=parse_instant(arguments.since) if arguments.since else None,
                until=parse_instant(arguments.until) if arguments.until else None,
            )
        )
        return 0
    if arguments.command == "evidence-materialize":
        document = materialize_gitlab(
            arguments.profile,
            arguments.source,
            parse_instant(arguments.since),
            parse_instant(arguments.until),
        )
        emit(document)
        return 0 if document["complete"] else 2
    if arguments.command == "artifact-record":
        emit(
            record_artifact(
                arguments.profile,
                Path(arguments.target),
                input_path=Path(arguments.input) if arguments.input else None,
                since=parse_instant(arguments.since) if arguments.since else None,
                until=parse_instant(arguments.until) if arguments.until else None,
                sources=arguments.source,
            )
        )
        return 0
    raise EvidenceError("a supported subcommand is required")


def record_command(arguments: argparse.Namespace) -> dict[str, Any]:
    evidence: bytes | None = None
    if arguments.evidence is not None:
        if arguments.incomplete:
            raise EvidenceError("--evidence requires a complete collection")
        path = regular_file(Path(arguments.evidence), "evidence input")
        raw = path.read_bytes()
        try:
            json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvidenceError("evidence input must be valid JSON") from exc
        evidence = raw
    return record_coverage(
        arguments.profile,
        arguments.source,
        arguments.kind,
        arguments.location,
        since=parse_instant(arguments.since) if arguments.since else None,
        until=parse_instant(arguments.until) if arguments.until else None,
        at=parse_instant(arguments.at) if arguments.at else None,
        complete=not arguments.incomplete,
        evidence=evidence,
        label=arguments.label,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        arguments = parser.parse_args(argv)
        return run_command(arguments)
    except EvidenceError as exc:
        return fail("invalid_input", str(exc))
    except OSError as exc:
        return fail("io_error", f"local I/O failed: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
