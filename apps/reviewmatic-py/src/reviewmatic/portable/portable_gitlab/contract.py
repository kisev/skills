#!/usr/bin/env python3
"""Canonical, GET-only GitLab evidence and local publication-plan contract."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import re
import selectors
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn, cast
from urllib.parse import quote as urlquote
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from collections.abc import Callable

try:
    from ..state_artifacts import (
        command_without_execution_status,
        ensure_private_directory,
        markdown_body,
        render_mutation_command,
        versioned_markdown,
        xdg_state_home,
    )
except ImportError:
    _state_path = Path(__file__).with_name("state_artifacts.py")
    if not _state_path.exists():
        _state_path = Path(__file__).parents[1] / "state_artifacts.py"
    _state_spec = importlib.util.spec_from_file_location("state_artifacts", _state_path)
    if _state_spec is None or _state_spec.loader is None:
        raise ImportError("state_artifacts runtime is unavailable")
    _state_module = importlib.util.module_from_spec(_state_spec)
    _state_spec.loader.exec_module(_state_module)
    markdown_body = _state_module.markdown_body
    command_without_execution_status = _state_module.command_without_execution_status
    ensure_private_directory = _state_module.ensure_private_directory
    render_mutation_command = _state_module.render_mutation_command
    versioned_markdown = _state_module.versioned_markdown
    xdg_state_home = _state_module.xdg_state_home

MAX_BYTES = 8 * 1024 * 1024
MAX_PAGES = 1_000
MAX_CI_PIPELINES = 20
MAX_CI_JOB_PAGES = 5
MAX_CI_TRACES = 50
MAX_TRACE_BYTES = 64 * 1024
MAX_TRACE_HEADER_BYTES = 64 * 1024
MAX_HTTP_SEPARATOR_BYTES = len(b"\r\n\r\n")
TRACE_TIMEOUT_SECONDS = 45
PROCESS_CLEANUP_TIMEOUT_SECONDS = 1
MAX_PIPELINE_DEPTH = 5
ARTIFACT_VERSION = 2
ARTIFACT_SCHEMA_NAME = "artifact-contracts-v2.schema.json"
URL_RE = re.compile(
    r"^https://(?P<host>[^/?#]+)/(?P<project>.+?)/-/(?P<kind>issues|merge_requests)/(?P<iid>[1-9][0-9]*)/?$"
)
SECRET_RE = re.compile(r"(?i)(token|password|secret|private[_-]?token)\s*[=:]\s*[^\s,]+")
JSON_SECRET_RE = re.compile(
    r"(?i)([\"'](?:authorization|password|secret|private[_-]?token|api[_-]?key|"
    r"access[_-]?key(?:[_-]?id)?|client[_-]?secret|aws_session_token)[\"']\s*:\s*)"
    r"([\"'])[^\r\n]*?\2"
)
AUTHORIZATION_RE = re.compile(r"(?im)(\bauthorization\s*:\s*)[^\r\n]+")
CLOUD_CREDENTIAL_RE = re.compile(
    r"(?i)\b((?:AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN|"
    r"GOOGLE_API_KEY|AZURE_CLIENT_ID|AZURE_CLIENT_SECRET)\s*[=:]\s*)[^\s,]+"
)
URL_CREDENTIAL_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^@\s/]+@")
PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
LABEL_ROLE_VALUES = {
    "change_type": {"release", "feature", "bug", "maintenance", "documentation", "security"},
    "workflow_state": {
        "in_progress",
        "review",
        "blocked",
        "completed",
        "declined",
        "needs_info",
        "stale",
    },
    "urgency": {"emergency", "urgent", "standard", "low"},
    "impact": {"critical", "high", "medium", "low"},
    "compatibility": {"major", "minor", "patch"},
    "origin": {"internal", "external", "inner_source"},
}
LABEL_ROLE_ALIASES = {
    "change_type": "change_type",
    "type": "change_type",
    "kind": "change_type",
    "category": "change_type",
    "workflow_state": "workflow_state",
    "status": "workflow_state",
    "state": "workflow_state",
    "workflow": "workflow_state",
    "urgency": "urgency",
    "priority": "urgency",
    "impact": "impact",
    "risk": "impact",
    "severity": "impact",
    "compatibility": "compatibility",
    "semver": "compatibility",
    "version": "compatibility",
    "origin": "origin",
    "source": "origin",
}
LABEL_VALUE_ALIASES = {
    "change_type": {
        "release": "release",
        "delivery": "release",
        "feature": "feature",
        "enhancement": "feature",
        "capability": "feature",
        "bug": "bug",
        "defect": "bug",
        "fix": "bug",
        "maintenance": "maintenance",
        "chore": "maintenance",
        "refactor": "maintenance",
        "technical": "maintenance",
        "tech_debt": "maintenance",
        "documentation": "documentation",
        "docs": "documentation",
        "security": "security",
        "vulnerability": "security",
    },
    "workflow_state": {
        "in_progress": "in_progress",
        "progress": "in_progress",
        "doing": "in_progress",
        "development": "in_progress",
        "review": "review",
        "review_ready": "review",
        "ready_for_review": "review",
        "blocked": "blocked",
        "on_hold": "blocked",
        "completed": "completed",
        "done": "completed",
        "closed": "completed",
        "declined": "declined",
        "rejected": "declined",
        "wontfix": "declined",
        "needs_info": "needs_info",
        "need_info": "needs_info",
        "waiting_for_info": "needs_info",
        "stale": "stale",
        "inactive": "stale",
    },
    "urgency": {
        "emergency": "emergency",
        "p0": "emergency",
        "blocker": "emergency",
        "critical": "emergency",
        "urgent": "urgent",
        "p1": "urgent",
        "high": "urgent",
        "standard": "standard",
        "p2": "standard",
        "normal": "standard",
        "medium": "standard",
        "low": "low",
        "p3": "low",
    },
    "impact": {
        "critical": "critical",
        "s1": "critical",
        "high": "high",
        "s2": "high",
        "medium": "medium",
        "s3": "medium",
        "low": "low",
        "s4": "low",
    },
    "compatibility": {
        "major": "major",
        "breaking": "major",
        "minor": "minor",
        "feature": "minor",
        "patch": "patch",
        "fix": "patch",
    },
    "origin": {
        "internal": "internal",
        "team": "internal",
        "external": "external",
        "customer": "external",
        "inner_source": "inner_source",
        "innersource": "inner_source",
        "community": "inner_source",
    },
}
PROFILES = {
    "task-triage": {"issues"},
    "task-review": {"issues", "merge_requests"},
    "task-prepare": {"issues"},
    "mr-prepare": {"merge_requests"},
    "code-review": {"merge_requests", "local"},
    "release-prepare": {"merge_requests"},
    "release-review": {"merge_requests"},
}
ARTIFACT_KINDS = {
    "evidence_snapshot",
    "release_inventory",
    "review_context",
    "publication_plan",
    "review_plan",
    "analysis_report",
    "context_package",
    "critic_receipt",
    "review_decision",
    "release_readiness",
    "finalize_report",
    "local_wip_snapshot",
    "local_review_report",
}


class WorkflowError(ValueError):
    """Expected contract or collection failure."""


class ContractArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise WorkflowError(message)


def parse_semver(
    value: object,
) -> tuple[int, int, int, tuple[str, ...], tuple[str, ...]] | None:
    if not isinstance(value, str) or not value or value.strip() != value:
        return None
    if value.count("+") > 1:
        return None
    version, separator, build_value = value.partition("+")
    if separator and not build_value:
        return None
    core, separator, prerelease_value = version.partition("-")
    if separator and not prerelease_value:
        return None
    core_values = core.split(".")
    if len(core_values) != 3 or any(
        len(item) > 64 or re.fullmatch(r"0|[1-9][0-9]*", item) is None for item in core_values
    ):
        return None

    def identifiers(raw: str, *, prerelease: bool) -> tuple[str, ...] | None:
        if not raw:
            return ()
        values = tuple(raw.split("."))
        if any(re.fullmatch(r"[0-9A-Za-z-]+", item) is None for item in values):
            return None
        if prerelease and any(
            re.fullmatch(r"[0-9]+", item) is not None and len(item) > 1 and item.startswith("0")
            for item in values
        ):
            return None
        return values

    prerelease_values = identifiers(prerelease_value, prerelease=True)
    build_values = identifiers(build_value, prerelease=False)
    if prerelease_values is None or build_values is None:
        return None
    major, minor, patch = (int(item) for item in core_values)
    return major, minor, patch, prerelease_values, build_values


def redact(value: str) -> str:
    redacted = PRIVATE_KEY_RE.sub("[REDACTED PRIVATE KEY]", value)
    redacted = JSON_SECRET_RE.sub(r"\1\2[REDACTED]\2", redacted)
    redacted = AUTHORIZATION_RE.sub(r"\1[REDACTED]", redacted)
    redacted = CLOUD_CREDENTIAL_RE.sub(r"\1[REDACTED]", redacted)
    redacted = URL_CREDENTIAL_RE.sub(r"\1[REDACTED]@", redacted)
    return SECRET_RE.sub(r"\1=[REDACTED]", redacted)


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def error(code: str, message: str, exit_code: int = 2) -> int:
    print(redact(message), file=sys.stderr)
    emit(
        {"status": "error", "error": {"code": code, "message": redact(message), "retryable": False}}
    )
    return exit_code


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def capabilities(profile: str) -> int:
    emit(
        {
            "schema_version": 1,
            "payload_version": "2.0.0",
            "mutation": "local-write",
            "dry_run": True,
            "state_protocol": "private-content-addressed-artifacts",
            "external_tools": {
                "glab": shutil.which("glab") is not None,
                "git": shutil.which("git") is not None,
            },
            "destructive_flags": [],
            "profile": profile,
            "external_mutations": False,
        }
    )
    return 0


def parse_target(value: str, expected: set[str]) -> dict[str, object]:
    parsed = urlsplit(value)
    match = URL_RE.fullmatch(value)
    if (
        parsed.scheme != "https"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or match is None
        or match.group("kind") not in expected
    ):
        raise WorkflowError("target must be one exact HTTPS GitLab issue or merge request URL")
    project = match.group("project")
    if not project or any(part in {"", ".", ".."} for part in project.split("/")):
        raise WorkflowError("target project path is unsafe")
    return {
        "url": value,
        "hostname": match.group("host").lower(),
        "project_path": project,
        "kind": match.group("kind"),
        "iid": int(match.group("iid")),
    }


def parse_project(value: str) -> dict[str, object]:
    parsed = urlsplit(value)
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or len(parts) < 2
        or "-" in parts
        or any(part in {".", ".."} for part in parts)
    ):
        raise WorkflowError("project must be an exact HTTPS GitLab project URL")
    return {
        "url": value.rstrip("/"),
        "hostname": parsed.hostname.lower(),
        "project_path": "/".join(parts),
        "kind": "new_issue",
        "iid": 0,
    }


def private_directory(path: Path) -> Path:
    try:
        return ensure_private_directory(path, xdg_state_home())
    except (OSError, ValueError) as error:
        raise WorkflowError("artifact directory must be a private real directory") from error


def state_directory(profile: str, target: dict[str, object]) -> Path:
    """Collection ownership is target identity, never the calling profile."""
    if profile not in PROFILES:
        raise WorkflowError("workflow profile is unsafe")
    home = xdg_state_home()
    identity = f"{target.get('hostname', 'local')}:{target.get('project_id', target.get('project_path', 'local'))}:{target.get('kind', 'local')}:{target.get('iid', 'local')}"
    return private_directory(
        home / "agent-skills" / "gitlab" / hashlib.sha256(identity.encode()).hexdigest()[:32]
    )


def artifact_root(path: Path) -> Path:
    home = xdg_state_home()
    state_base = private_directory(home / "agent-skills")
    base = private_directory(state_base / "gitlab")
    candidate = private_directory(path)
    try:
        relative = candidate.relative_to(base)
    except ValueError as exc:
        try:
            legacy = candidate.relative_to(state_base)
        except ValueError:
            raise WorkflowError(
                "artifact root is outside canonical GitLab collection state"
            ) from exc
        if (
            len(legacy.parts) == 2
            and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", legacy.parts[0])
            and re.fullmatch(r"[a-f0-9]{20}", legacy.parts[1])
        ):
            return candidate
        raise WorkflowError("artifact root is outside canonical GitLab collection state") from exc
    if len(relative.parts) != 1 or not re.fullmatch(r"[a-f0-9]{32}", relative.name):
        raise WorkflowError("artifact root is unsafe")
    return candidate


def regular_file(path: Path, label: str) -> Path:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise WorkflowError(f"{label} is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise WorkflowError(f"{label} must be a regular non-symlink file")
    if metadata.st_size > MAX_BYTES:
        raise WorkflowError(f"{label} exceeds the size limit")
    return path.resolve()


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(regular_file(path, label).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"{label} must contain a JSON object") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"{label} must contain a JSON object")
    return value


def write_json(path: Path, value: object) -> None:
    """Only mutable state pointers use this helper; artifacts use write_artifact."""
    write_bytes(path, canonical(value))


def reject_envelope_wrapper(value: object, label: str) -> None:
    """Agent inputs often arrive wrapped in the artifact envelope the agent saw in recorded state."""
    if not isinstance(value, dict):
        return
    keys = set(value)
    if (
        "payload" in keys
        and isinstance(value["payload"], dict)
        and keys <= {"payload", "schema", "kind"}
    ):
        extra = ", ".join(sorted(keys - {"payload"})) or "schema"
        raise WorkflowError(
            f"{label} must contain the artifact payload itself, not the "
            f"{{schema, payload}} envelope wrapper; pass the object stored in the payload field "
            f"(drop the envelope keys {extra})"
        )


def write_bytes(path: Path, content: bytes) -> None:
    """Atomically replace a private mutable file."""
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise WorkflowError("state path must be a regular non-symlink file")
    target = path.resolve()
    if target.parent != path.parent.resolve():
        raise WorkflowError("state path escapes its directory")
    temporary = target.with_name(f".{target.name}.{os.urandom(8).hex()}.tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)


def write_artifact(root: Path, kind: str, payload: dict[str, Any]) -> tuple[Path, str]:
    if kind not in ARTIFACT_KINDS:
        raise WorkflowError("unknown artifact kind")
    envelope = {
        "schema": f"portable-gitlab/{kind}/v2",
        "schema_version": ARTIFACT_VERSION,
        "kind": kind,
        "created_at": datetime.now(UTC).isoformat(),
        "payload": payload,
    }
    validate_v2_artifact(envelope, kind)
    # Timestamps are state metadata; the address covers the complete immutable document.
    content = canonical(envelope)
    content_digest = hashlib.sha256(content).hexdigest()
    directory = private_directory(root / "artifacts" / kind)
    path = directory / f"{content_digest}.json"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if regular_file(path, "artifact").read_bytes() != content:
            raise WorkflowError("content-addressed artifact conflict")
        return path, content_digest
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return path, content_digest


def write_companion(path: Path, content: str) -> tuple[Path, str]:
    """Write a private immutable companion next to its content-addressed envelope."""
    data = content.encode()
    content_digest = hashlib.sha256(data).hexdigest()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if regular_file(path, "Markdown companion").read_bytes() != data:
            raise WorkflowError("immutable Markdown companion conflict")
        return path.resolve(), content_digest
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return path.resolve(), content_digest


def artifact_payload(path: Path, kind: str) -> tuple[dict[str, Any], dict[str, Any]]:
    value = read_json(path, "artifact")
    if (
        value.get("schema") == f"portable-gitlab/{kind}/v2"
        and value.get("kind") == kind
        and value.get("schema_version") == ARTIFACT_VERSION
        and isinstance(value.get("payload"), dict)
    ):
        validate_v2_artifact(value, kind)
        return value, value["payload"]
    # v1 snapshots are readable/finalizable but never rewritten or migrated.
    if value.get("schema_version") == 1 and kind == "evidence_snapshot":
        return value, value
    raise WorkflowError("artifact schema is invalid")


def exact_keys(value: object, required: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != required:
        raise WorkflowError(f"{label} has unknown or missing fields")
    return value


def nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def is_digest(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def is_sha(value: object, *, nullable: bool = False) -> bool:
    return (nullable and value is None) or (
        isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{1,128}", value) is not None
    )


def component_is_valid(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "items",
        "complete",
        "errors",
        "pages",
        "truncated",
    }:
        return False
    return (
        isinstance(value["items"], list)
        and isinstance(value["complete"], bool)
        and isinstance(value["errors"], list)
        and all(isinstance(item, str) for item in value["errors"])
        and isinstance(value["pages"], int)
        and value["pages"] >= 0
        and isinstance(value["truncated"], bool)
    )


def is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def key_set(value: dict[str, object]) -> set[str]:
    return set(value)


def sets_equal(left: set[object], right: set[object]) -> bool:
    return left == right


def equal_json(left: object, right: object) -> bool:
    return canonical(left) == canonical(right)


def full_match(pattern: str, value: str) -> bool:
    return re.fullmatch(pattern, value) is not None


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def findings_are_valid(value: object) -> bool:
    if not isinstance(value, list):
        return False
    legacy = {"id"}
    detailed = {
        "id",
        "severity",
        "summary",
        "risk",
        "evidence",
        "consequence",
        "relation_to_change",
        "minimum_fix",
    }
    detail_fields = detailed - {"id", "severity", "evidence"}
    return all(
        isinstance(item, dict)
        and (set(item) == legacy or set(item) == detailed)
        and nonempty_string(item.get("id"))
        and (
            set(item) == legacy
            or (
                item.get("severity") in {"critical", "high", "medium", "low"}
                and all(nonempty_string(item.get(key)) for key in detail_fields)
                and isinstance(item.get("evidence"), list)
                and bool(item["evidence"])
                and all(nonempty_string(entry) for entry in item["evidence"])
            )
        )
        for item in value
    )


def detailed_findings_are_valid(value: object) -> bool:
    return findings_are_valid(value) and all(
        isinstance(item, dict) and set(item) != {"id"} for item in cast("list[object]", value)
    )


def duplicate_detailed_finding_ids(value: object) -> list[list[str]]:
    if not detailed_findings_are_valid(value):
        return []
    groups: dict[str, list[str]] = {}
    for finding in cast("list[dict[str, Any]]", value):
        content = {key: item for key, item in finding.items() if key != "id"}
        groups.setdefault(digest(content), []).append(cast("str", finding["id"]))
    return [item_ids for item_ids in groups.values() if len(item_ids) > 1]


def thread_decisions_are_valid(value: object) -> bool:
    legacy = {"id", "url", "state", "assessment", "rationale", "outcome", "proposed_response"}
    current = legacy | {"last_note_id", "last_note_body_sha256", "thread_sha256"}
    structured = current | {"suggestion_applicable"}
    fix = current | {"fix_mode", "patch", "fixing_commit"}
    materialized_fix = fix | {"patch_path", "patch_sha256"}
    allowed = (legacy, current, structured, fix, materialized_fix)
    extensible = {
        "suggestions",
        "split_rationale",
        "patch_reason",
        "severity",
        "user_confirmation",
        "routing_response",
    }
    if not isinstance(value, list):
        return False
    return all(
        _thread_decision_is_valid(
            item, allowed, extensible, legacy, structured, fix, materialized_fix
        )
        for item in value
    )


def _thread_decision_is_valid(
    item: object,
    allowed: tuple[set[str], set[str], set[str], set[str], set[str]],
    extensible: set[str],
    legacy: set[str],
    structured: set[str],
    fix: set[str],
    materialized_fix: set[str],
) -> bool:
    if not isinstance(item, dict):
        return False
    keys = set(item) - extensible
    if not any(keys == candidate for candidate in allowed):
        return False
    if not (
        nonempty_string(item.get("id"))
        and nonempty_string(item.get("url"))
        and nonempty_string(item.get("rationale"))
    ):
        return False
    if item.get("state") not in {"open", "resolved", "plain"}:
        return False
    if item.get("assessment") not in {
        "accepted",
        "fixed",
        "false_positive",
        "duplicate",
        "not_related",
        "question",
        "neutral",
    }:
        return False
    if item.get("outcome") not in {"no_publication", "local_fix", "reply", "resolve", "reopen"}:
        return False
    if item.get("state") == "open" and item.get("outcome") == "no_publication":
        return False
    if item.get("proposed_response") is not None and not nonempty_string(
        item.get("proposed_response")
    ):
        return False
    if keys != legacy and not (
        item.get("last_note_id") is not None
        and is_digest(item.get("last_note_body_sha256"))
        and is_digest(item.get("thread_sha256"))
    ):
        return False
    if keys == structured and not isinstance(item.get("suggestion_applicable"), bool):
        return False
    if keys in (fix, materialized_fix):
        fixing_commit = item.get("fixing_commit")
        fixing_commit_valid = fixing_commit is None or (
            isinstance(fixing_commit, dict)
            and set(fixing_commit) == {"title", "url"}
            and all(nonempty_string(fixing_commit[key]) for key in ("title", "url"))
        )
        patch = item.get("patch")
        patch_valid = (item.get("fix_mode") == "patch" and nonempty_string(patch)) or (
            item.get("fix_mode") != "patch" and patch is None
        )
        if (
            item.get("fix_mode") not in {"suggestion", "patch", "not_required"}
            or not fixing_commit_valid
            or not patch_valid
        ):
            return False
    if keys == materialized_fix:
        materialized_valid = (
            item.get("fix_mode") == "patch"
            and nonempty_string(item.get("patch_path"))
            and isinstance(item.get("patch_path"), str)
            and item["patch_path"].startswith("/")
            and is_digest(item.get("patch_sha256"))
            and isinstance(item.get("patch"), str)
            and sha256_text(item["patch"]) == item["patch_sha256"]
        ) or (
            item.get("fix_mode") != "patch"
            and item.get("patch_path") is None
            and item.get("patch_sha256") is None
        )
        if not materialized_valid:
            return False
    return True


def finding_publications_are_valid(value: object, require_fixes: bool = False) -> bool:
    legacy = {"finding_id", "revision", "type", "path", "line", "old_line", "body"}
    fixed = legacy | {"fix_mode", "patch", "patch_path", "patch_sha256"}
    allowed = (fixed,) if require_fixes else (legacy, fixed)
    extensible = {"suggestions", "split_rationale", "patch_reason", "thread_id"}
    if not isinstance(value, list):
        return False
    return all(_finding_publication_is_valid(item, allowed, extensible, legacy) for item in value)


def _finding_publication_is_valid(
    item: object,
    allowed: tuple[set[str], ...],
    extensible: set[str],
    legacy: set[str],
) -> bool:
    if not isinstance(item, dict):
        return False
    keys = set(item) - extensible
    if not any(keys == candidate for candidate in allowed):
        return False
    if not nonempty_string(item.get("finding_id")) or not is_plain_int(item.get("revision")):
        return False
    if cast("int", item["revision"]) < 1:
        return False
    if item.get("type") == "existing_thread":
        return (
            nonempty_string(item.get("thread_id"))
            and nonempty_string(item.get("body"))
            and item.get("fix_mode") == "not_required"
            and item.get("patch") is None
            and item.get("patch_path") is None
            and item.get("patch_sha256") is None
            and item.get("path") is None
            and item.get("line") is None
            and item.get("old_line") is None
        )
    if item.get("type") not in {"general", "line", "local_fix"} or not nonempty_string(
        item.get("body")
    ):
        return False
    if keys == legacy:
        return True
    if item.get("fix_mode") not in {"suggestion", "patch"}:
        return False
    if item.get("fix_mode") == "patch":
        return (
            nonempty_string(item.get("patch"))
            and nonempty_string(item.get("patch_path"))
            and isinstance(item.get("patch_path"), str)
            and item["patch_path"].startswith("/")
            and is_digest(item.get("patch_sha256"))
            and isinstance(item.get("patch"), str)
            and sha256_text(item["patch"]) == item["patch_sha256"]
        )
    return (
        item.get("patch") is None
        and item.get("patch_path") is None
        and item.get("patch_sha256") is None
    )


def metadata_assessment_item_is_valid(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"status", "rationale", "recommendation"}
        and value.get("status") in {"ok", "needs_change", "unverified"}
        and nonempty_string(value.get("rationale"))
        and (value.get("recommendation") is None or nonempty_string(value.get("recommendation")))
    )


def mr_metadata_assessment_is_valid(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {"observed", "assessment"}:
        return False
    observed, assessment = value["observed"], value["assessment"]
    fields = {"title", "description", "labels", "workflow_state"}
    assessment_fields = fields | {"overall"}
    return (
        isinstance(observed, dict)
        and set(observed) == fields
        and isinstance(observed.get("title"), str)
        and (observed.get("description") is None or isinstance(observed.get("description"), str))
        and isinstance(observed.get("labels"), list)
        and all(isinstance(item, str) for item in observed["labels"])
        and nonempty_string(observed.get("workflow_state"))
        and isinstance(assessment, dict)
        and set(assessment) == assessment_fields
        and all(metadata_assessment_item_is_valid(assessment[field]) for field in assessment_fields)
    )


def review_chat_assessment_is_valid(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {"necessity", "relevance", "change"}:
        return False
    necessity, relevance = value["necessity"], value["relevance"]
    return (
        isinstance(necessity, dict)
        and set(necessity) == {"status", "rationale"}
        and necessity.get("status") in {"supported", "doubtful", "unconfirmed"}
        and nonempty_string(necessity.get("rationale"))
        and isinstance(relevance, dict)
        and set(relevance) == {"status", "rationale"}
        and relevance.get("status") in {"current", "partly_outdated", "outdated"}
        and nonempty_string(relevance.get("rationale"))
        and nonempty_string(value.get("change"))
    )


def review_metadata_labels(locale: str) -> dict[str, str]:
    return (
        {
            "title": "Заголовок",
            "description": "Описание",
            "workflow_state": "Состояние",
            "overall": "Итог оформления",
        }
        if locale == "ru"
        else {
            "title": "Title",
            "description": "Description",
            "workflow_state": "State",
            "overall": "Metadata summary",
        }
    )


def review_action_labels(locale: str) -> dict[str, str]:
    return (
        {
            "add": "Добавить",
            "remove": "Убрать",
            "reply": "Опубликовать ответ:",
            "resolve": "После успешной публикации закрыть тред:",
            "reopen": "После успешной публикации переоткрыть тред:",
        }
        if locale == "ru"
        else {
            "add": "Add",
            "remove": "Remove",
            "reply": "Publish reply:",
            "resolve": "After successful publication, resolve the thread:",
            "reopen": "After successful publication, reopen the thread:",
        }
    )


def code_review_presentation(
    locale: str, role: str, verdict: str, incremental_mode: str
) -> dict[str, Any]:
    if locale not in {"en", "ru"}:
        raise WorkflowError("review locale must be en or ru")
    if role not in {"author", "reviewer"} or verdict not in {"ready", "not_ready", "blocked"}:
        raise WorkflowError("review presentation identity is invalid")
    if locale == "ru":
        return {
            "title": "План публикации ревью",
            "incremental_notice": "Проведено инкрементальное ревью."
            if incremental_mode == "incremental"
            else None,
            "target_label": "MR",
            "role_label": "Роль",
            "role_value": "автор MR" if role == "author" else "ревьюер чужого MR",
            "verdict_label": "Итог",
            "verdict_value": {
                "ready": "можно сливать",
                "not_ready": "нужны изменения",
                "blocked": "нужно решение владельца",
            }[verdict],
            "metadata_heading": "Оформление MR",
            "labels_heading": "Лейблы проекта",
            "previous_findings_heading": "Сверка предыдущих обнаружений",
            "open_threads_heading": "Открытые треды",
            "closed_threads_heading": "Закрытые треды",
            "local_fixes_heading": "Локальные исправления",
            "new_findings_heading": "Новые обнаружения",
            "recommended_issues_heading": "Рекомендуемые задачи",
            "checked_heading": "Проверено без публикации",
            "architecture_heading": "Архитектурная оценка",
            "semver_heading": "Влияние на SemVer",
            "checks_heading": "Проверки",
            "publication_heading": "Ручная публикация",
            "no_items": "Нет.",
            "publication_warning": "Команды не выполнялись.",
            "previous_table_headers": ["ID", "Было", "Стало", "Основание", "Действие"],
            "evidence_label": "Доказательство",
            "relation_label": "Связь с изменением",
            "severity_labels": {
                "critical": "Критическая",
                "high": "Высокая",
                "medium": "Средняя",
                "low": "Низкая",
            },
            "recovery_label": "Если ответ опубликован, а состояние не изменилось, выполни только:",
        }
    return {
        "title": "Code review publication plan",
        "incremental_notice": "Incremental review completed."
        if incremental_mode == "incremental"
        else None,
        "target_label": "Target",
        "role_label": "Role",
        "role_value": "author of this MR"
        if role == "author"
        else "reviewer of another author's MR",
        "verdict_label": "Verdict",
        "verdict_value": {
            "ready": "ready to merge",
            "not_ready": "changes required",
            "blocked": "owner decision required",
        }[verdict],
        "metadata_heading": "MR metadata",
        "labels_heading": "Project labels",
        "previous_findings_heading": "Previous findings",
        "open_threads_heading": "Open threads",
        "closed_threads_heading": "Closed threads",
        "local_fixes_heading": "Local fixes",
        "new_findings_heading": "New findings",
        "recommended_issues_heading": "Recommended issues",
        "checked_heading": "Reviewed without publication",
        "architecture_heading": "Architecture assessment",
        "semver_heading": "SemVer impact",
        "checks_heading": "Checks",
        "publication_heading": "Manual publication preflight",
        "no_items": "None.",
        "publication_warning": "No command was executed.",
        "previous_table_headers": [
            "ID",
            "Previous status",
            "Current status",
            "Rationale",
            "Action",
        ],
        "evidence_label": "Evidence",
        "relation_label": "Relation to change",
        "severity_labels": {
            "critical": "Critical",
            "high": "High",
            "medium": "Medium",
            "low": "Low",
        },
        "recovery_label": "If the response succeeds but the state change fails, run only:",
    }


def code_review_chat_labels(locale: str) -> dict[str, Any]:
    if locale == "ru":
        return {
            "title": "### Оценка MR",
            "blocked_title": "### Ревью заблокировано",
            "role": "Роль",
            "necessity": "Необходимость",
            "relevance": "Актуальность",
            "change": "Изменение",
            "architecture": "Архитектура",
            "semver": "SemVer",
            "metadata": "Оформление MR",
            "verdict": "Итог",
            "checkout": "Checkout ревью",
            "plan": "План публикации",
            "findings": "Замечания",
            "none": "Замечаний нет.",
            "stage": "Этап",
            "reason": "Причина",
            "next_action": "Следующее действие",
            "metadata_values": {
                "ok": "готово",
                "needs_change": "нужны изменения",
                "unverified": "нужен контекст",
            },
            "necessity_values": {
                "supported": "обоснована",
                "doubtful": "сомнительна",
                "unconfirmed": "не подтверждена",
            },
            "relevance_values": {
                "current": "актуально",
                "partly_outdated": "частично устарело",
                "outdated": "устарело",
            },
        }
    if locale != "en":
        raise WorkflowError("review locale must be en or ru")
    return {
        "title": "### MR assessment",
        "blocked_title": "### Review blocked",
        "role": "Role",
        "necessity": "Necessity",
        "relevance": "Relevance",
        "change": "Change",
        "architecture": "Architecture",
        "semver": "SemVer",
        "metadata": "MR metadata",
        "verdict": "Verdict",
        "checkout": "Review checkout",
        "plan": "Publication plan",
        "findings": "Findings",
        "none": "No findings.",
        "stage": "Stage",
        "reason": "Reason",
        "next_action": "Next action",
        "metadata_values": {
            "ok": "ready",
            "needs_change": "changes needed",
            "unverified": "context needed",
        },
        "necessity_values": {
            "supported": "supported",
            "doubtful": "doubtful",
            "unconfirmed": "unconfirmed",
        },
        "relevance_values": {
            "current": "current",
            "partly_outdated": "partly outdated",
            "outdated": "outdated",
        },
    }


def _publication_bodies_valid(body_files: object, *, structured: bool) -> bool:
    if not isinstance(body_files, list):
        return False
    keys = (
        {"publication_id", "revision", "kind", "path", "sha256", "content"}
        if structured
        else {"publication_id", "revision", "kind", "path", "content"}
    )
    return all(
        isinstance(item, dict)
        and set(item) == keys
        and nonempty_string(item.get("publication_id"))
        and is_plain_int(item.get("revision"))
        and cast("int", item["revision"]) >= 1
        and item.get("kind") in {"finding", "thread", "issue"}
        and nonempty_string(item.get("path"))
        and isinstance(item.get("path"), str)
        and item["path"].startswith("/")
        and nonempty_string(item.get("content"))
        and (
            not structured
            or (
                is_digest(item.get("sha256"))
                and isinstance(item.get("content"), str)
                and sha256_text(item["content"]) == item["sha256"]
            )
        )
        for item in body_files
    )


def review_publication_preview_is_valid(value: object) -> bool:
    legacy_keys = {"mr_state", "warning", "preflight_command", "body_files", "commands"}
    current_keys = legacy_keys | {"preflight_path", "preflight_sha256"}
    structured_keys = {
        "mr_state",
        "warning",
        "preflight_path",
        "preflight_sha256",
        "body_files",
        "actions",
    }
    manual_keys = {"mr_state", "warning", "body_files", "actions"}
    if not isinstance(value, dict):
        return False
    keys = set(value)
    if keys == manual_keys:
        return _manual_preview_is_valid(value)
    if keys == structured_keys:
        return _structured_preview_is_valid(value)
    if keys not in (legacy_keys, current_keys):
        return False
    legacy = keys == legacy_keys
    if (
        not nonempty_string(value.get("mr_state"))
        or not nonempty_string(value.get("warning"))
        or not nonempty_string(value.get("preflight_command"))
        or (
            not legacy
            and (
                not nonempty_string(value.get("preflight_path"))
                or not isinstance(value.get("preflight_path"), str)
                or not value["preflight_path"].startswith("/")
                or not is_digest(value.get("preflight_sha256"))
            )
        )
        or not isinstance(value.get("body_files"), list)
        or not isinstance(value.get("commands"), list)
    ):
        return False
    body_files, commands = value["body_files"], value["commands"]
    if legacy:
        bodies_valid = all(
            isinstance(item, dict)
            and set(item) == {"finding_id", "path", "sha256", "content"}
            and nonempty_string(item.get("finding_id"))
            and nonempty_string(item.get("path"))
            and isinstance(item.get("path"), str)
            and item["path"].startswith("/")
            and is_digest(item.get("sha256"))
            and nonempty_string(item.get("content"))
            and isinstance(item.get("content"), str)
            and sha256_text(item["content"]) == item["sha256"]
            for item in body_files
        )
        commands_valid = all(
            isinstance(item, dict)
            and set(item) == {"finding_id", "command"}
            and nonempty_string(item.get("finding_id"))
            and nonempty_string(item.get("command"))
            for item in commands
        )
        if not bodies_valid or not commands_valid:
            return False
        body_ids = [item["finding_id"] for item in body_files if isinstance(item, dict)]
        command_ids = [item["finding_id"] for item in commands if isinstance(item, dict)]
        return (
            len(body_ids) == len(set(body_ids))
            and len(command_ids) == len(set(command_ids))
            and equal_json(body_ids, command_ids)
        )
    if not _publication_bodies_valid(body_files, structured=True):
        return False
    outcomes = {
        "create_general",
        "create_line",
        "create_issue",
        "update_issue",
        "reply",
        "resolve",
        "reopen",
    }
    commands_valid = all(
        isinstance(item, dict)
        and set(item)
        == {"publication_id", "revision", "kind", "outcome", "command", "recovery_command"}
        and nonempty_string(item.get("publication_id"))
        and is_plain_int(item.get("revision"))
        and cast("int", item["revision"]) >= 1
        and item.get("kind") in {"finding", "thread", "issue"}
        and item.get("outcome") in outcomes
        and nonempty_string(item.get("command"))
        and (item.get("recovery_command") is None or nonempty_string(item.get("recovery_command")))
        for item in commands
    )
    if not commands_valid:
        return False
    body_ids = [item.get("publication_id") for item in body_files if isinstance(item, dict)]
    command_ids = [item.get("publication_id") for item in commands if isinstance(item, dict)]
    typed_bodies = [item for item in body_files if isinstance(item, dict)]
    typed_commands = [item for item in commands if isinstance(item, dict)]
    return (
        len(body_ids) == len(set(body_ids))
        and len(command_ids) == len(set(command_ids))
        and equal_json(body_ids, command_ids)
        and all(
            body.get("revision") == command.get("revision")
            and body.get("kind") == command.get("kind")
            for body, command in zip(typed_bodies, typed_commands, strict=False)
        )
    )


def _manual_preview_is_valid(value: dict[str, Any]) -> bool:
    body_files, actions = value.get("body_files"), value.get("actions")
    if (
        not nonempty_string(value.get("mr_state"))
        or not nonempty_string(value.get("warning"))
        or not isinstance(body_files, list)
        or not isinstance(actions, list)
    ):
        return False
    bodies_valid = all(
        isinstance(item, dict)
        and set(item) == {"publication_id", "revision", "kind", "path", "content"}
        and nonempty_string(item.get("publication_id"))
        and is_plain_int(item.get("revision"))
        and cast("int", item["revision"]) >= 1
        and item.get("kind") in {"finding", "thread", "issue"}
        and nonempty_string(item.get("path"))
        and isinstance(item.get("path"), str)
        and item["path"].startswith("/")
        and nonempty_string(item.get("content"))
        for item in body_files
    )
    actions_valid = all(
        isinstance(item, dict)
        and set(item) == {"id", "kind", "publication_id", "operation", "command", "path", "line"}
        and nonempty_string(item.get("id"))
        and item.get("kind") in {"finding", "thread", "issue", "labels"}
        and item.get("operation")
        in {
            "create_general",
            "create_line",
            "create_issue",
            "reply",
            "resolve",
            "reopen",
            "update_labels",
        }
        and nonempty_string(item.get("command"))
        for item in actions
    )
    if not bodies_valid or not actions_valid:
        return False
    action_ids = [item.get("id") for item in actions if isinstance(item, dict)]
    manual_body_ids = {item.get("publication_id") for item in body_files if isinstance(item, dict)}
    manual_action_body_ids = {
        item.get("publication_id")
        for item in actions
        if isinstance(item, dict) and item.get("publication_id") is not None
    }
    return len(action_ids) == len(set(action_ids)) and manual_body_ids == manual_action_body_ids


def _structured_preview_is_valid(value: dict[str, Any]) -> bool:
    body_files, actions = value.get("body_files"), value.get("actions")
    if (
        not nonempty_string(value.get("mr_state"))
        or not nonempty_string(value.get("warning"))
        or not nonempty_string(value.get("preflight_path"))
        or not isinstance(value.get("preflight_path"), str)
        or not value["preflight_path"].startswith("/")
        or not is_digest(value.get("preflight_sha256"))
        or not isinstance(body_files, list)
        or not isinstance(actions, list)
    ):
        return False
    if not _publication_bodies_valid(body_files, structured=True):
        return False
    operations = {
        "create_general",
        "create_line",
        "create_issue",
        "update_issue",
        "reply",
        "resolve",
        "reopen",
        "update_labels",
    }
    for item in actions:
        if (
            not isinstance(item, dict)
            or set(item)
            != {
                "id",
                "sha256",
                "kind",
                "publication_id",
                "revision",
                "operation",
                "command",
                "spec",
            }
            or not nonempty_string(item.get("id"))
            or not is_digest(item.get("sha256"))
            or item.get("kind") not in {"finding", "thread", "issue", "labels"}
            or item.get("operation") not in operations
            or not nonempty_string(item.get("command"))
        ):
            return False
        spec = item.get("spec")
        if (
            not isinstance(spec, dict)
            or item["sha256"] != digest(spec)
            or set(spec)
            != {
                "schema",
                "preflight_sha256",
                "operation",
                "publication",
                "body",
                "expected",
                "mutation",
            }
            or spec.get("schema") != "code-review/publication-action/v1"
            or spec.get("preflight_sha256") != value.get("preflight_sha256")
            or spec.get("operation") != item.get("operation")
            or not isinstance(spec.get("expected"), dict)
            or set(spec["expected"]) != {"thread", "note", "prior_marker", "issue"}
            or not isinstance(spec.get("mutation"), dict)
        ):
            return False
        mutation = spec["mutation"]
        if item["kind"] == "labels":
            if not (
                item.get("publication_id") is None
                and item.get("revision") is None
                and item.get("operation") == "update_labels"
                and spec.get("publication") is None
                and spec.get("body") is None
                and set(mutation) == {"add", "remove", "proposed"}
                and all(
                    isinstance(mutation.get(key), list)
                    and all(isinstance(label, str) for label in mutation[key])
                    for key in ("add", "remove", "proposed")
                )
            ):
                return False
            if set(mutation["add"]) & set(mutation["remove"]):
                return False
            continue
        if item.get("kind") not in {"finding", "thread", "issue"}:
            return False
        if (
            not nonempty_string(item.get("publication_id"))
            or not is_plain_int(item.get("revision"))
            or cast("int", item["revision"]) < 1
            or not isinstance(spec.get("publication"), dict)
            or not equal_json(
                spec["publication"],
                {
                    "id": item["publication_id"],
                    "revision": item["revision"],
                    "kind": item["kind"],
                },
            )
            or not isinstance(spec.get("body"), dict)
            or set(spec["body"]) != {"path", "sha256"}
            or not isinstance(spec["body"].get("path"), str)
            or not spec["body"]["path"].startswith("/")
            or not is_digest(spec["body"].get("sha256"))
        ):
            return False
    action_ids = [item.get("id") for item in actions if isinstance(item, dict)]
    body_identities = {
        "\x00".join(
            [
                str(item.get("publication_id")),
                str(item.get("revision")),
                str(item.get("kind")),
                str(item.get("path")),
                str(item.get("sha256")),
            ]
        )
        for item in body_files
        if isinstance(item, dict)
    }
    action_identity_list = []
    for item in actions:
        if not isinstance(item, dict) or item.get("kind") == "labels":
            continue
        body = cast("dict[str, Any]", item["spec"])["body"]
        action_identity_list.append(
            "\x00".join(
                [
                    str(item.get("publication_id")),
                    str(item.get("revision")),
                    str(item.get("kind")),
                    str(body.get("path")),
                    str(body.get("sha256")),
                ]
            )
        )
    return (
        len(action_ids) == len(set(action_ids))
        and sum(1 for item in actions if isinstance(item, dict) and item.get("kind") == "labels")
        <= 1
        and body_identities == set(action_identity_list)
    )


def incremental_review_is_valid(value: object) -> bool:
    required = {
        "contract_version",
        "requested",
        "mode",
        "reason",
        "incremental_baseline",
        "previous_findings",
        "previous_finding_publications",
        "previous_recommended_issues",
        "previous_finding_ledger",
        "previous_publication_ledger",
        "previous_thread_decisions",
        "previous_rejected_candidates",
        "reconsidered_rejected_candidates",
        "incremental_delta",
        "incremental_delta_digest",
        "critic_required",
        "fallback_reasons",
    }
    if not isinstance(value, dict) or set(value) != required:
        return False
    mode = value["mode"]
    delta = value["incremental_delta"]
    baseline = value["incremental_baseline"]
    list_keys = (
        "previous_findings",
        "previous_finding_publications",
        "previous_recommended_issues",
        "previous_finding_ledger",
        "previous_publication_ledger",
        "previous_thread_decisions",
        "previous_rejected_candidates",
        "reconsidered_rejected_candidates",
    )
    delta_list_keys = (
        "changed_paths",
        "changed_thread_ids",
        "unchanged_thread_ids",
        "changed_note_ids",
        "unchanged_note_ids",
        "metadata_fields",
    )
    if (
        value["contract_version"] != 1
        or value["requested"] not in {"auto", "off"}
        or mode not in {"full", "incremental", "unchanged"}
        or not nonempty_string(value.get("reason"))
        or not isinstance(baseline, dict)
        or set(baseline) != {"plan_path", "plan_digest", "state_digest"}
        or (
            baseline.get("state_digest") is not None and not is_digest(baseline.get("state_digest"))
        )
        or not isinstance(value.get("critic_required"), bool)
        or not isinstance(value.get("fallback_reasons"), list)
        or not all(isinstance(item, str) for item in value["fallback_reasons"])
        or not all(isinstance(value.get(key), list) for key in list_keys)
        or not isinstance(delta, dict)
        or not is_digest(value.get("incremental_delta_digest"))
        or set(delta)
        != {
            "from_head",
            "to_head",
            "changed_paths",
            "changed_thread_ids",
            "unchanged_thread_ids",
            "changed_note_ids",
            "unchanged_note_ids",
            "metadata_fields",
            "pipelines_changed",
        }
        or not is_sha(delta.get("from_head"), nullable=True)
        or not is_sha(delta.get("to_head"), nullable=True)
        or not all(
            isinstance(delta.get(key), list) and all(isinstance(item, str) for item in delta[key])
            for key in delta_list_keys
        )
        or not isinstance(delta.get("pipelines_changed"), bool)
        or value["incremental_delta_digest"] != digest(delta)
    ):
        return False
    has_baseline = nonempty_string(baseline.get("plan_path")) and is_digest(
        baseline.get("plan_digest")
    )
    if mode == "full":
        return (
            baseline.get("plan_path") is None
            and baseline.get("plan_digest") is None
            and value["critic_required"] is False
            and all(len(value[key]) == 0 for key in list_keys)
        )
    return (
        has_baseline
        and is_sha(delta.get("to_head"))
        and value["critic_required"] == (mode == "incremental")
    )


def semantic_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def semantic_role(value: str) -> str | None:
    return LABEL_ROLE_ALIASES.get(semantic_token(value))


def semantic_value(role: str, value: str) -> str | None:
    return LABEL_VALUE_ALIASES.get(role, {}).get(semantic_token(value))


def label_semantics(value: object) -> tuple[str, str] | None:
    if not isinstance(value, dict) or not nonempty_string(value.get("name")):
        return None
    name = cast("str", value["name"])
    description = value.get("description")
    if isinstance(description, str):
        marker = re.search(
            r"semantic[-_ ]role\s*[:=]\s*([^;\n]+)\s*;\s*semantic[-_ ]value\s*[:=]\s*([^;\n]+)",
            description,
            re.IGNORECASE,
        )
        if marker is not None:
            role = semantic_role(marker.group(1))
            item_value = semantic_value(role, marker.group(2)) if role is not None else None
            if role is not None and item_value in LABEL_ROLE_VALUES[role]:
                return role, item_value
            return None
    parts = re.split(r"::|:|/|=", name, maxsplit=1)
    if len(parts) != 2:
        return None
    role = semantic_role(parts[0])
    item_value = semantic_value(role, parts[1]) if role is not None else None
    if role is None or item_value not in LABEL_ROLE_VALUES[role]:
        return None
    return role, item_value


def label_intent_is_valid(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != set(LABEL_ROLE_VALUES):
        return False
    return all(
        item is None or (isinstance(item, str) and item in LABEL_ROLE_VALUES[role])
        for role, item in value.items()
    )


def review_labels(bundle: dict[str, Any], intent: dict[str, str | None]) -> dict[str, Any]:
    labels_component = bundle.get("labels")
    object_value = bundle.get("object")
    if not isinstance(labels_component, dict) or not isinstance(object_value, dict):
        raise WorkflowError("label evidence is unavailable")
    raw_current = object_value.get("labels")
    if not isinstance(raw_current, list) or not all(isinstance(item, str) for item in raw_current):
        raise WorkflowError("current MR labels are invalid")
    current = cast("list[str]", raw_current)
    semantics_by_name: dict[str, set[tuple[str, str]]] = {}
    for item in cast("list[object]", labels_component.get("items", [])):
        semantics = label_semantics(item)
        if semantics is None or not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        semantics_by_name.setdefault(item["name"], set()).add(semantics)
    resolved_by_name = {
        name: next(iter(values)) for name, values in semantics_by_name.items() if len(values) == 1
    }
    candidates: dict[tuple[str, str], list[str]] = {}
    for name, semantics in resolved_by_name.items():
        candidates.setdefault(semantics, []).append(name)
    for names in candidates.values():
        names.sort(key=str.casefold)
    add: list[str] = []
    remove: list[str] = []
    unresolved: list[str] = []
    decisions: list[dict[str, Any]] = []
    catalog_complete = labels_component.get("complete") is True
    for role in LABEL_ROLE_VALUES:
        requested = intent[role]
        current_for_role = [
            name for name in current if resolved_by_name.get(name, (None, None))[0] == role
        ]
        if requested is None:
            decisions.append(
                {
                    "role": role,
                    "intent": None,
                    "current": current_for_role,
                    "desired_label": None,
                    "action": "keep",
                    "reason": "no semantic intent supplied",
                }
            )
            continue
        matching = candidates.get((role, requested), []) if catalog_complete else []
        if not catalog_complete or len(matching) > 1:
            reason = (
                "project label catalog is incomplete"
                if not catalog_complete
                else "multiple project labels match the same semantic intent"
            )
            unresolved.append(f"{role}={requested}: {reason}")
            decisions.append(
                {
                    "role": role,
                    "intent": requested,
                    "current": current_for_role,
                    "desired_label": None,
                    "action": "unresolved",
                    "reason": reason,
                }
            )
            continue
        if not matching:
            decisions.append(
                {
                    "role": role,
                    "intent": requested,
                    "current": current_for_role,
                    "desired_label": None,
                    "action": "unsupported",
                    "reason": "semantic role and value are not represented in the project catalog",
                }
            )
            continue
        desired_label = matching[0]
        role_remove = [name for name in current_for_role if name != desired_label]
        for name in role_remove:
            if name not in remove:
                remove.append(name)
        if desired_label not in current and desired_label not in add:
            add.append(desired_label)
        decisions.append(
            {
                "role": role,
                "intent": requested,
                "current": current_for_role,
                "desired_label": desired_label,
                "action": "change" if role_remove or desired_label in add else "keep",
                "reason": "unique semantic match in the project label catalog",
            }
        )
    proposed = [name for name in current if name not in remove]
    proposed.extend(name for name in add if name not in proposed)
    return {
        "complete": catalog_complete and not unresolved,
        "intent": intent,
        "current": current,
        "proposed": proposed,
        "add": add,
        "remove": remove,
        "decisions": decisions,
        "unresolved": unresolved,
    }


def label_review_is_valid(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "complete",
        "intent",
        "current",
        "proposed",
        "add",
        "remove",
        "decisions",
        "unresolved",
    }:
        return False
    if (
        not isinstance(value["complete"], bool)
        or not label_intent_is_valid(value["intent"])
        or not all(
            isinstance(value[key], list) and all(isinstance(item, str) for item in value[key])
            for key in ("current", "proposed", "add", "remove", "unresolved")
        )
        or not isinstance(value["decisions"], list)
    ):
        return False
    decisions = cast("list[object]", value["decisions"])
    required = {"role", "intent", "current", "desired_label", "action", "reason"}
    if not all(
        isinstance(item, dict)
        and set(item) == required
        and isinstance(item.get("role"), str)
        and item["role"] in LABEL_ROLE_VALUES
        and (
            item.get("intent") is None
            or (
                isinstance(item.get("intent"), str)
                and item["intent"] in LABEL_ROLE_VALUES[item["role"]]
            )
        )
        and isinstance(item.get("current"), list)
        and all(isinstance(name, str) for name in item["current"])
        and (item.get("desired_label") is None or isinstance(item.get("desired_label"), str))
        and item.get("action") in {"keep", "change", "unsupported", "unresolved"}
        and nonempty_string(item.get("reason"))
        for item in decisions
    ):
        return False
    typed_decisions = cast("list[dict[str, Any]]", decisions)
    roles = [item["role"] for item in typed_decisions]
    current = cast("list[str]", value["current"])
    add = cast("list[str]", value["add"])
    remove = cast("list[str]", value["remove"])
    expected = [name for name in current if name not in remove]
    expected.extend(name for name in add if name not in expected)
    return (
        len(roles) == len(LABEL_ROLE_VALUES)
        and set(roles) == set(LABEL_ROLE_VALUES)
        and all(name in current for item in typed_decisions for name in item["current"])
        and all(name in current for name in remove)
        and all(name in value["proposed"] for name in add)
        and not set(add).intersection(remove)
        and len(add) == len(set(add))
        and len(remove) == len(set(remove))
        and (
            value["complete"] is False
            or (
                not value["unresolved"]
                and all(item["action"] != "unresolved" for item in typed_decisions)
            )
        )
        and value["proposed"] == expected
    )


def code_review_label_review_is_valid(value: object) -> bool:
    required = {
        "complete",
        "catalog_sha256",
        "catalog",
        "assessments",
        "current",
        "add",
        "remove",
        "proposed",
        "unresolved",
        "semver",
    }
    if not isinstance(value, dict) or set(value) != required:
        return False
    if (
        value.get("complete") is not True
        or not is_digest(value.get("catalog_sha256"))
        or not isinstance(value.get("catalog"), list)
        or not isinstance(value.get("assessments"), list)
        or not all(
            isinstance(value.get(key), list)
            and len(value[key]) == len(set(value[key]))
            and all(isinstance(item, str) for item in value[key])
            for key in ("current", "add", "remove", "proposed", "unresolved")
        )
        or not isinstance(value.get("semver"), dict)
        or set(value["semver"]) != {"impact", "candidates", "selected"}
        or value["semver"].get("impact")
        not in {"major", "minor", "patch", "none", "not_applicable"}
        or not isinstance(value["semver"].get("candidates"), list)
        or not all(isinstance(item, str) for item in value["semver"]["candidates"])
        or (
            value["semver"].get("selected") is not None
            and not isinstance(value["semver"].get("selected"), str)
        )
    ):
        return False
    catalog = cast("list[object]", value["catalog"])
    assessments = cast("list[object]", value["assessments"])
    if not all(
        isinstance(item, dict)
        and set(item) == {"name", "description"}
        and nonempty_string(item.get("name"))
        and (item.get("description") is None or isinstance(item.get("description"), str))
        for item in catalog
    ) or not all(
        isinstance(item, dict)
        and set(item) == {"name", "description", "status", "rationale", "current"}
        and nonempty_string(item.get("name"))
        and (item.get("description") is None or isinstance(item.get("description"), str))
        and item.get("status") in {"applicable", "inapplicable", "unresolved"}
        and nonempty_string(item.get("rationale"))
        and isinstance(item.get("current"), bool)
        for item in assessments
    ):
        return False
    catalog_names = [cast("dict[str, Any]", item)["name"] for item in catalog]
    assessment_by_name = {
        cast("dict[str, Any]", item)["name"]: cast("dict[str, Any]", item) for item in assessments
    }
    current = cast("list[str]", value["current"])
    add = cast("list[str]", value["add"])
    remove = cast("list[str]", value["remove"])
    proposed = sorted((set(current) - set(remove)) | set(add), key=str.casefold)
    return (
        value["catalog_sha256"] == digest(value["catalog"])
        and len(catalog_names) == len(set(catalog_names)) == len(assessment_by_name)
        and set(catalog_names) == set(assessment_by_name)
        and set(current).issubset(catalog_names)
        and set(add).issubset(catalog_names)
        and set(remove).issubset(current)
        and not set(add) & set(remove)
        and proposed == value["proposed"]
        and set(value["unresolved"])
        == {name for name, item in assessment_by_name.items() if item["status"] == "unresolved"}
        and all((name in current) is item["current"] for name, item in assessment_by_name.items())
    )


def companions_are_valid(value: object) -> bool:
    if not isinstance(value, list):
        return False
    names: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"name", "content", "sha256"}:
            return False
        name, content, content_digest = item["name"], item["content"], item["sha256"]
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}", name) is None
            or name in names
            or not isinstance(content, str)
            or not is_digest(content_digest)
            or hashlib.sha256(content.encode()).hexdigest() != content_digest
        ):
            return False
        names.add(name)
    return True


def release_content_shape_is_valid(value: object) -> bool:
    required = {
        "title",
        "description",
        "version",
        "announcement",
        "illustration_prompt",
        "label_intent",
        "milestone_title",
        "contributors",
        "reviewers",
        "illustration_style",
        "work_items",
    }
    if not isinstance(value, dict) or set(value) != required:
        return False
    style = value.get("illustration_style")
    work_items = value.get("work_items")
    contributors = value.get("contributors")
    reviewers = value.get("reviewers")
    return not (
        not all(
            nonempty_string(value.get(key))
            for key in (
                "title",
                "description",
                "announcement",
                "illustration_prompt",
                "milestone_title",
            )
        )
        or parse_semver(value.get("version")) is None
        or not label_intent_is_valid(value.get("label_intent"))
        or not isinstance(contributors, list)
        or not all(nonempty_string(item) for item in contributors)
        or len(contributors) != len(set(contributors))
        or not isinstance(reviewers, list)
        or not all(
            isinstance(item, str) and re.fullmatch(r"@[A-Za-z0-9_.-]+", item) is not None
            for item in reviewers
        )
        or len(reviewers) != len(set(reviewers))
        or not isinstance(style, dict)
        or set(style) != {"preset", "reference", "custom"}
        or style.get("preset") not in {"pixel_art", "literary", "neutral_abstract", "custom"}
        or (style.get("reference") is not None and not nonempty_string(style["reference"]))
        or (style.get("custom") is not None and not nonempty_string(style["custom"]))
        or (style["preset"] == "literary") != nonempty_string(style.get("reference"))
        or (style["preset"] == "custom") != nonempty_string(style.get("custom"))
        or not isinstance(work_items, list)
    )


def release_content_is_valid(value: object, inventory: dict[str, Any]) -> bool:
    if not release_content_shape_is_valid(value):
        return False
    content = cast("dict[str, Any]", value)
    contributors = cast("list[str]", content["contributors"])
    reviewers = cast("list[str]", content["reviewers"])
    work_items = cast("list[dict[str, Any]]", content["work_items"])
    version = parse_semver(content["version"])
    previous_ref = inventory.get("previous_ref")
    compatibility = cast("dict[str, object]", content["label_intent"]).get("compatibility")
    if version is None or version[3] or version[4] or version[0] < 1:
        return False
    if previous_ref is None:
        if version[:3] != (1, 0, 0) or compatibility != "major":
            return False
    elif isinstance(previous_ref, str) and re.fullmatch(r"[0-9a-fA-F]{40}", previous_ref):
        if compatibility not in {"major", "minor", "patch"}:
            return False
    else:
        previous = (
            parse_semver(previous_ref[1:])
            if isinstance(previous_ref, str) and previous_ref.startswith("v")
            else None
        )
        if previous is None or previous[3] or previous[4] or previous[0] < 1:
            return False
        expected_versions = {
            "major": (previous[0] + 1, 0, 0),
            "minor": (previous[0], previous[1] + 1, 0),
            "patch": (previous[0], previous[1], previous[2] + 1),
        }
        if (
            not isinstance(compatibility, str)
            or expected_versions.get(compatibility) != version[:3]
        ):
            return False
    contributor_values = {
        item.get("display") for item in inventory.get("contributors", []) if isinstance(item, dict)
    }
    reviewer_values = {
        f"@{item['username']}"
        for item in inventory.get("reviewers", [])
        if isinstance(item, dict) and nonempty_string(item.get("username"))
    }
    if not set(contributors).issubset(contributor_values) or not set(reviewers).issubset(
        reviewer_values
    ):
        return False
    candidates = {
        (item.get("project_id"), item.get("iid"))
        for item in inventory.get("work_item_candidates", [])
        if isinstance(item, dict)
    }
    decisions: set[tuple[int, int]] = set()
    for item in work_items:
        if (
            not isinstance(item, dict)
            or set(item) != {"project_id", "iid", "action", "rationale", "uncertain", "comment"}
            or not isinstance(item.get("project_id"), int)
            or isinstance(item.get("project_id"), bool)
            or not isinstance(item.get("iid"), int)
            or isinstance(item.get("iid"), bool)
            or item["project_id"] < 1
            or item["iid"] < 1
            or item.get("action") not in {"close", "comment", "no_action"}
            or not nonempty_string(item.get("rationale"))
            or not isinstance(item.get("uncertain"), bool)
            or (item.get("comment") is not None and not nonempty_string(item["comment"]))
            or (item["action"] == "comment") != nonempty_string(item.get("comment"))
        ):
            return False
        identity = (item["project_id"], item["iid"])
        if identity in decisions:
            return False
        decisions.add(identity)
    return decisions == candidates


def release_requests_are_valid(value: object) -> bool:
    if not isinstance(value, list):
        return False
    request_ids: set[str] = set()
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"id", "stage", "operation", "command", "assets"}
            or not nonempty_string(item.get("id"))
            or item["id"] in request_ids
            or item.get("stage") not in {"pre_merge", "post_merge"}
            or not nonempty_string(item.get("operation"))
            or (item.get("command") is not None and not nonempty_string(item["command"]))
            or not isinstance(item.get("assets"), list)
        ):
            return False
        request_ids.add(item["id"])
        for asset in item["assets"]:
            if (
                not isinstance(asset, dict)
                or set(asset) != {"role", "name", "path", "sha256", "content"}
                or not nonempty_string(asset.get("role"))
                or not nonempty_string(asset.get("name"))
                or not nonempty_string(asset.get("path"))
                or not is_digest(asset.get("sha256"))
                or not isinstance(asset.get("content"), str)
                or not cast("str", asset["name"]).startswith(cast("str", asset["sha256"]))
                or hashlib.sha256(cast("str", asset["content"]).encode()).hexdigest()
                != asset["sha256"]
            ):
                return False
    return True


def release_target_state_is_valid(value: object, stage: object, post_merge_sha: object) -> bool:
    if stage == "pre_merge":
        return value is None and post_merge_sha is None
    return (
        stage == "post_merge"
        and isinstance(value, dict)
        and set(value) == {"tag_name", "tag_exists", "tag_sha", "release_exists"}
        and nonempty_string(value.get("tag_name"))
        and isinstance(value.get("tag_exists"), bool)
        and is_sha(value.get("tag_sha"), nullable=True)
        and isinstance(value.get("release_exists"), bool)
        and value["tag_exists"] == (value["tag_sha"] is not None)
        and value["tag_sha"] in {None, post_merge_sha}
        and value["release_exists"] is False
    )


def artifact_schema() -> dict[str, Any]:
    """Load the only canonical schema from source or its materialized skill copy."""
    candidates = (
        Path(__file__).with_name(ARTIFACT_SCHEMA_NAME),
        Path(__file__).parents[2] / "references" / "portable-gitlab-contracts-v2.schema.json",
    )
    for path in candidates:
        if path.is_file() and not path.is_symlink():
            schema = read_json(path, "artifact schema")
            if schema.get("$id") == "https://kisev.dev/schemas/portable-gitlab-artifacts/v2":
                return schema
    raise WorkflowError("canonical artifact schema is unavailable")


def schema_valid(schema: dict[str, Any], value: object, root: dict[str, Any]) -> bool:
    """Validate the JSON Schema features used by the canonical artifact contract."""
    reference = schema.get("$ref")
    if isinstance(reference, str):
        prefix = "#/$defs/"
        if not reference.startswith(prefix):
            return False
        definition = root.get("$defs", {}).get(reference.removeprefix(prefix))
        return isinstance(definition, dict) and schema_valid(definition, value, root)
    negated = schema.get("not")
    if isinstance(negated, dict) and schema_valid(negated, value, root):
        return False
    condition = schema.get("if")
    if isinstance(condition, dict):
        branch = schema.get("then") if schema_valid(condition, value, root) else schema.get("else")
        if isinstance(branch, dict) and not schema_valid(branch, value, root):
            return False
    if "allOf" in schema and not all(
        isinstance(item, dict) and schema_valid(item, value, root) for item in schema["allOf"]
    ):
        return False
    if (
        "oneOf" in schema
        and sum(
            isinstance(item, dict) and schema_valid(item, value, root) for item in schema["oneOf"]
        )
        != 1
    ):
        return False
    if "anyOf" in schema and not any(
        isinstance(item, dict) and schema_valid(item, value, root) for item in schema["anyOf"]
    ):
        return False
    if "const" in schema and value != schema["const"]:
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    expected_type = schema.get("type")
    if expected_type == "null" and value is not None:
        return False
    if expected_type == "object" and not isinstance(value, dict):
        return False
    if expected_type == "array" and not isinstance(value, list):
        return False
    if expected_type == "string" and not isinstance(value, str):
        return False
    if expected_type == "boolean" and not isinstance(value, bool):
        return False
    if expected_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
        return False
    if isinstance(value, str):
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.fullmatch(pattern, value) is None:
            return False
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            return False
        if schema.get("format") == "date-time" and not _iso_format_is_valid(value):
            return False
    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and isinstance(schema.get("minimum"), int)
        and value < schema["minimum"]
    ):
        return False
    if isinstance(value, list):
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            return False
        if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
            return False
        item_schema = schema.get("items")
        if isinstance(item_schema, dict) and not all(
            schema_valid(item_schema, item, root) for item in value
        ):
            return False
    if isinstance(value, dict):
        required = schema.get("required", [])
        if not isinstance(required, list) or not all(
            isinstance(key, str) and key in value for key in required
        ):
            return False
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return False
        if schema.get("additionalProperties") is False and not set(value).issubset(properties):
            return False
        if not all(
            not isinstance(properties.get(key), dict)
            or schema_valid(cast("dict[str, Any]", properties[key]), item, root)
            for key, item in value.items()
            if key in properties
        ):
            return False
    return True


def _ci_job_assessment_is_valid(item: object) -> bool:
    return (
        isinstance(item, dict)
        and set(item)
        == {"project_id", "pipeline_id", "job_id", "classification", "rationale", "trace_evidence"}
        and all(is_plain_int(item[key]) for key in ("project_id", "pipeline_id", "job_id"))
        and item["classification"]
        in {"process_gate", "code_failure", "infrastructure_failure", "unknown"}
        and nonempty_string(item["rationale"])
        and nonempty_string(item["trace_evidence"])
    )


def _review_response_is_valid(item: object) -> bool:
    return (
        isinstance(item, dict)
        and schema_valid({"$ref": "#/$defs/response"}, item, artifact_schema())
        and nonempty_string(item.get("id"))
        and item.get("decision") in {"accept", "reject"}
        and nonempty_string(item.get("reason"))
    )


def _iso_format_is_valid(value: str) -> bool:
    """Strict ISO-8601 calendar date-time check; the canonical timestamp contract."""
    match = re.fullmatch(
        r"^(\d{4})-(\d{2})-(\d{2})"
        r"(?:([^0-9])(\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d+))?)?"
        r"(Z|[+-]\d{2}(?::?\d{2})?(?::\d{2}(?:\.\d+)?)?)?)?$",
        value,
    )
    if match is None:
        return False
    year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
    leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
    days_in_month = [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if month < 1 or month > 12 or day < 1 or day > days_in_month[month - 1]:
        return False
    hour = int(match.group(5)) if match.group(5) is not None else 0
    minute = int(match.group(6)) if match.group(6) is not None else 0
    second = int(match.group(7)) if match.group(7) is not None else 0
    if hour > 23 or minute > 59 or second > 59:
        return False
    zone = match.group(9)
    if zone is not None and zone != "Z":
        offset_hours = int(zone[1:3])
        offset_minutes = int(zone[-2:]) if len(zone) >= 5 else 0
        if offset_minutes > 59 or offset_hours >= 24:
            return False
        if offset_hours == 23 and offset_minutes > 0:
            return False
    return True


_SCHEMA_ISSUE_LOCATORS: list[Callable[[dict[str, Any], Any], list[dict[str, str]]]] = []


def register_schema_issue_locator(
    locator: Callable[[dict[str, Any], Any], list[dict[str, str]]],
) -> None:
    """Let a host explain schema failures; the validator alone decides validity."""
    _SCHEMA_ISSUE_LOCATORS[:] = [locator]


def validate_v2_artifact(value: dict[str, Any], kind: str) -> None:
    """Enforce the canonical v2 schema without a runtime-only dependency."""
    schema = artifact_schema()
    if not schema_valid(schema, value, schema):
        located = (
            "\n".join(
                f" - {issue['path']}: {issue['message']}"
                for issue in _SCHEMA_ISSUE_LOCATORS[0](schema, value)[:8]
            )
            if _SCHEMA_ISSUE_LOCATORS
            else ""
        )
        raise WorkflowError(
            f"artifact does not satisfy the canonical schema:\n{located}"
            if located
            else "artifact does not satisfy the canonical schema"
        )
    envelope = exact_keys(
        value, {"schema", "schema_version", "kind", "created_at", "payload"}, "artifact"
    )
    if (
        envelope["schema"] != f"portable-gitlab/{kind}/v2"
        or envelope["schema_version"] != ARTIFACT_VERSION
        or envelope["kind"] != kind
        or not nonempty_string(envelope["created_at"])
        or not isinstance(envelope["payload"], dict)
    ):
        raise WorkflowError("artifact schema is invalid")
    if not _iso_format_is_valid(cast("str", envelope["created_at"])):
        raise WorkflowError("artifact timestamp is schema-invalid")
    payload = cast("dict[str, Any]", envelope["payload"])
    if kind == "evidence_snapshot":
        exact_keys(
            payload,
            {
                "schema_version",
                "profile",
                "external_mutations",
                "target",
                "project",
                "object",
                "labels",
                "changed_files",
                "commits",
                "pipelines",
                "discussions",
                "head_sha",
                "base_sha",
                "start_sha",
                "artifact_root",
                "prepared_at",
                "components_complete",
                "retrieval_complete",
            },
            "evidence payload",
        )
        required_components = {
            "project",
            "labels",
            "object",
            "changed_files",
            "commits",
            "pipelines",
            "discussions",
        }
        if (
            payload["schema_version"] != ARTIFACT_VERSION
            or payload["external_mutations"] is not False
            or not all(isinstance(payload[key], dict) for key in ("target", "project", "object"))
            or not all(
                component_is_valid(payload[key])
                for key in ("labels", "changed_files", "commits", "pipelines", "discussions")
            )
            or not all(
                is_sha(payload[key], nullable=True) for key in ("head_sha", "base_sha", "start_sha")
            )
            or not nonempty_string(payload["profile"])
            or not nonempty_string(payload["artifact_root"])
            or not nonempty_string(payload["prepared_at"])
            or not isinstance(payload["components_complete"], dict)
            or set(payload["components_complete"]) != required_components
            or not all(isinstance(item, bool) for item in payload["components_complete"].values())
            or not isinstance(payload["retrieval_complete"], bool)
        ):
            raise WorkflowError("evidence payload is schema-invalid")
    elif kind == "local_wip_snapshot":
        exact_keys(
            payload,
            {
                "schema_version",
                "profile",
                "external_mutations",
                "repo_root",
                "base_sha",
                "head_sha",
                "ref",
                "sections",
                "artifact_root",
                "retrieval_complete",
            },
            "local WIP payload",
        )
        if (
            payload["schema_version"] != ARTIFACT_VERSION
            or payload["external_mutations"] is not False
            or not nonempty_string(payload["profile"])
            or not nonempty_string(payload["repo_root"])
            or not is_sha(payload["base_sha"])
            or not is_sha(payload["head_sha"])
            or (payload["ref"] is not None and not nonempty_string(payload["ref"]))
            or not isinstance(payload["sections"], dict)
            or set(payload["sections"]) != {"committed", "staged", "unstaged", "untracked"}
            or not nonempty_string(payload["artifact_root"])
            or not isinstance(payload["retrieval_complete"], bool)
        ):
            raise WorkflowError("local WIP payload is schema-invalid")
    elif kind == "review_context":
        legacy_required = {
            "schema_version",
            "profile",
            "external_mutations",
            "evidence_digest",
            "target",
            "role",
            "current_user_username",
            "mr_author_username",
            "discussions",
            "notes",
            "counts",
            "exact_git",
            "complete",
            "errors",
            "artifact_root",
            "prepared_at",
        }
        current_required = legacy_required | {"incremental", "issue_templates"}
        structured_required = current_required | {"current_user_id"}
        release_required = structured_required | {"release_evidence"}
        payload_keys = set(payload)
        if payload_keys not in (
            legacy_required,
            current_required,
            structured_required,
            release_required,
        ):
            raise WorkflowError("review context payload has unknown or missing fields")
        legacy_context = payload_keys == legacy_required
        structured_context = payload_keys in (structured_required, release_required)
        if payload_keys == release_required:
            from . import review_semver as _review_semver

            if not _review_semver.evidence_is_valid(payload["release_evidence"]):
                raise WorkflowError("review release evidence is schema-invalid")
        counts = payload["counts"]
        exact_git = payload["exact_git"]
        if (
            payload["schema_version"] != ARTIFACT_VERSION
            or payload["profile"] != "code-review"
            or payload["external_mutations"] is not False
            or not is_digest(payload["evidence_digest"])
            or not isinstance(payload["target"], dict)
            or payload["role"] not in {"author", "reviewer"}
            or (
                structured_context
                and (
                    not is_plain_int(payload["current_user_id"])
                    or cast("int", payload["current_user_id"]) < 1
                )
            )
            or not all(
                nonempty_string(payload[key])
                for key in (
                    "current_user_username",
                    "mr_author_username",
                    "artifact_root",
                    "prepared_at",
                )
            )
            or (payload["current_user_username"] == payload["mr_author_username"])
            != (payload["role"] == "author")
            or not all(isinstance(payload[key], list) for key in ("discussions", "notes", "errors"))
            or not all(isinstance(item, str) for item in payload["errors"])
            or (not legacy_context and not incremental_review_is_valid(payload["incremental"]))
            or not isinstance(payload["complete"], bool)
            or not isinstance(counts, dict)
            or set(counts)
            != {
                "discussions",
                "notes",
                "content_notes",
                "system_notes",
                "open_resolvable",
                "resolved_resolvable",
                "plain_discussions",
            }
            or not all(is_plain_int(item) and cast("int", item) >= 0 for item in counts.values())
            or not isinstance(exact_git, dict)
            or set(exact_git)
            != {"repo_root", "refs", "changed_paths", "diff_sha256", "complete", "errors"}
            or not nonempty_string(exact_git["repo_root"])
            or not isinstance(exact_git["refs"], dict)
            or not isinstance(exact_git["changed_paths"], list)
            or not all(isinstance(item, str) for item in exact_git["changed_paths"])
            or not (is_digest(exact_git["diff_sha256"]) or exact_git["diff_sha256"] is None)
            or not isinstance(exact_git["complete"], bool)
            or not isinstance(exact_git["errors"], list)
            or not all(isinstance(item, str) for item in exact_git["errors"])
        ):
            raise WorkflowError("review context payload is schema-invalid")
    elif kind == "release_inventory":
        required = {
            "schema_version",
            "profile",
            "external_mutations",
            "evidence_digest",
            "target",
            "repo_root",
            "project_id",
            "hostname",
            "head_sha",
            "component_target_branch",
            "previous_ref",
            "previous_ref_explicit",
            "previous_sha",
            "previous_tag",
            "revision_range",
            "commits",
            "merge_requests",
            "direct_commits",
            "contributors",
            "reviewers",
            "milestone_candidates",
            "work_item_candidates",
            "collection_completeness",
            "errors",
            "warnings",
            "complete",
            "artifact_root",
            "prepared_at",
            "counts",
        }
        exact_keys(payload, required, "release inventory payload")
        counts = payload["counts"]
        if (
            payload["schema_version"] != ARTIFACT_VERSION
            or payload["profile"] != "release-prepare"
            or payload["external_mutations"] is not False
            or not is_digest(payload["evidence_digest"])
            or not isinstance(payload["target"], dict)
            or not nonempty_string(payload["repo_root"])
            or not isinstance(payload["project_id"], int)
            or isinstance(payload["project_id"], bool)
            or payload["project_id"] < 1
            or not all(
                nonempty_string(payload[key])
                for key in ("hostname", "component_target_branch", "revision_range")
            )
            or not is_sha(payload["head_sha"])
            or (
                payload["previous_ref"] is not None and not nonempty_string(payload["previous_ref"])
            )
            or not isinstance(payload["previous_ref_explicit"], bool)
            or not is_sha(payload["previous_sha"], nullable=True)
            or (
                payload["previous_tag"] is not None
                and not isinstance(payload["previous_tag"], dict)
            )
            or not all(
                isinstance(payload[key], list)
                for key in (
                    "commits",
                    "merge_requests",
                    "direct_commits",
                    "contributors",
                    "reviewers",
                    "milestone_candidates",
                    "work_item_candidates",
                    "errors",
                    "warnings",
                )
            )
            or not isinstance(payload["collection_completeness"], dict)
            or set(payload["collection_completeness"])
            != {"component_merge_requests", "project_milestones", "work_items"}
            or not all(
                isinstance(item, bool) for item in payload["collection_completeness"].values()
            )
            or not isinstance(payload["complete"], bool)
            or not nonempty_string(payload["artifact_root"])
            or not nonempty_string(payload["prepared_at"])
            or not isinstance(counts, dict)
            or set(counts)
            != {
                "commits",
                "merge_requests",
                "direct_commits",
                "contributors",
                "reviewers",
                "milestone_candidates",
                "work_item_candidates",
                "errors",
                "warnings",
            }
            or not all(
                isinstance(item, int) and not isinstance(item, bool) and item >= 0
                for item in counts.values()
            )
        ):
            raise WorkflowError("release inventory payload is schema-invalid")
    elif kind == "publication_plan":
        required = {
            "profile",
            "target",
            "evidence_digest",
            "complete",
            "markdown",
            "plan_name",
            "external_mutations",
        }
        release_fields = {
            "inventory_digest",
            "release_version",
            "companions",
            "stage",
            "release_content",
            "requests",
            "post_merge_sha",
            "release_target_state",
        }
        label_fields = {"label_review"}
        profile = payload.get("profile")
        actual_keys = set(payload)
        if profile == "release-prepare":
            expected_keys = required | release_fields
            keys_valid = actual_keys == expected_keys or actual_keys == (
                expected_keys | label_fields
            )
        elif profile == "mr-prepare":
            expected_keys = required
            keys_valid = (
                actual_keys == expected_keys
                or actual_keys == (expected_keys | label_fields)
                or actual_keys == (expected_keys | label_fields | {"mr_content", "requests"})
            )
        else:
            expected_keys = required
            keys_valid = actual_keys == expected_keys
        if (
            not keys_valid
            or not nonempty_string(payload.get("profile"))
            or not isinstance(payload.get("target"), dict)
            or not is_digest(payload.get("evidence_digest"))
            or not isinstance(payload.get("markdown"), str)
            or not nonempty_string(payload.get("plan_name"))
            or not isinstance(payload["complete"], bool)
            or payload["external_mutations"] is not False
            or (
                payload.get("profile") == "release-prepare"
                and (
                    not is_digest(payload.get("inventory_digest"))
                    or parse_semver(payload.get("release_version")) is None
                    or not companions_are_valid(payload.get("companions"))
                    or payload.get("stage") not in {"pre_merge", "post_merge"}
                    or not release_content_shape_is_valid(payload.get("release_content"))
                    or payload.get("release_version")
                    != cast("dict[str, object]", payload.get("release_content"))["version"]
                    or not release_requests_are_valid(payload.get("requests"))
                    or not is_sha(payload.get("post_merge_sha"), nullable=True)
                    or (payload.get("stage") == "pre_merge")
                    != (payload.get("post_merge_sha") is None)
                    or not release_target_state_is_valid(
                        payload.get("release_target_state"),
                        payload.get("stage"),
                        payload.get("post_merge_sha"),
                    )
                )
            )
            or (
                "label_review" in payload
                and not (
                    code_review_label_review_is_valid(payload["label_review"])
                    if "mr_content" in payload
                    else label_review_is_valid(payload["label_review"])
                )
            )
            or (
                "mr_content" in payload
                and (
                    not isinstance(payload["mr_content"], dict)
                    or not isinstance(payload.get("requests"), list)
                    or not all(
                        isinstance(item, dict)
                        and set(item) == {"name", "content", "sha256", "field", "command"}
                        and all(isinstance(value, str) for value in item.values())
                        and item["field"] in {"title", "description", "labels"}
                        and is_digest(item["sha256"])
                        and item["name"] == f"{item['sha256']}-{item['field']}.json"
                        for item in payload["requests"]
                    )
                )
            )
        ):
            raise WorkflowError("publication plan payload is schema-invalid")
    elif kind == "review_plan":
        legacy_required = {
            "profile",
            "external_mutations",
            "evidence_digest",
            "context_digest",
            "decision_digest",
            "target",
            "role",
            "mode",
            "verdict",
            "complete",
            "summary",
            "architecture_assessment",
            "semver_impact",
            "semver_rationale",
            "mr_metadata_assessment",
            "publication_preview",
            "checks",
            "findings",
            "thread_decisions",
            "markdown",
        }
        minimal_required = legacy_required - {
            "semver_rationale",
            "mr_metadata_assessment",
            "publication_preview",
        }
        current_required = legacy_required | {
            "review_contract_version",
            "incremental",
            "presentation",
            "finding_publications",
            "previous_finding_assessments",
            "recommended_issues",
            "finding_ledger",
            "publication_ledger",
            "rejected_candidates",
            "rejected_candidate_assessments",
            "rejected_candidate_ledger",
        }
        structured_required = current_required | {"label_review"}
        final_required = structured_required | {"chat_assessment", "locale"}
        release_required = final_required | {"semver_assessment"}
        actual_keys = set(payload) - {"review_source"}
        if actual_keys not in (
            minimal_required,
            legacy_required,
            current_required,
            structured_required,
            final_required,
            release_required,
        ):
            raise WorkflowError("review plan payload has unknown or missing fields")
        structured_plan = actual_keys in (structured_required, final_required, release_required)
        final_plan = actual_keys in (final_required, release_required)
        release_plan = actual_keys == release_required
        minimal_plan = actual_keys == minimal_required
        legacy_plan = actual_keys not in (
            current_required,
            structured_required,
            final_required,
            release_required,
        )
        from . import review_semver as _review_semver

        if release_plan != (payload.get("review_contract_version") in (6, 7)) or (
            release_plan
            and (
                not _review_semver.assessment_is_valid(payload.get("semver_assessment"))
                or not code_review_label_review_is_valid(payload.get("label_review"))
                or cast("dict[str, Any]", payload["label_review"])["semver"]["impact"]
                != payload["semver_impact"]
            )
        ):
            raise WorkflowError("review plan SemVer assessment is invalid")
        list_keys = (
            "finding_publications",
            "previous_finding_assessments",
            "recommended_issues",
            "finding_ledger",
            "publication_ledger",
            "rejected_candidates",
            "rejected_candidate_assessments",
            "rejected_candidate_ledger",
        )
        version = payload.get("review_contract_version")
        thread_decisions = cast("list[object]", payload.get("thread_decisions", []))
        invalid = (
            payload["profile"] != "code-review"
            or (
                not legacy_plan
                and (version not in (2, 3, 4, 5, 6, 7) if structured_plan else version != 1)
            )
            or final_plan != (version in (4, 5, 6, 7))
            or payload["external_mutations"] is not False
            or not all(
                is_digest(payload[key])
                for key in ("evidence_digest", "context_digest", "decision_digest")
            )
            or not isinstance(payload["target"], dict)
            or payload["role"] not in {"author", "reviewer"}
            or not (
                payload["mode"] in {"fast", "normal", "deep"}
                if legacy_plan
                else payload["mode"] in {"fast", "normal", "deep", "incremental", "unchanged"}
            )
            or (not legacy_plan and not incremental_review_is_valid(payload["incremental"]))
            or payload["verdict"] not in {"ready", "not_ready", "blocked"}
            or not isinstance(payload["complete"], bool)
            or not all(
                nonempty_string(payload[key]) for key in ("summary", "architecture_assessment")
            )
            or payload["semver_impact"]
            not in {"major", "minor", "patch", "none", "not_applicable", "unknown"}
            or not isinstance(payload["checks"], list)
            or not all(nonempty_string(item) for item in payload["checks"])
            or not (
                findings_are_valid(payload["findings"])
                if minimal_plan
                else detailed_findings_are_valid(payload["findings"])
            )
            or not thread_decisions_are_valid(payload["thread_decisions"])
            or (
                structured_plan
                and (
                    not code_review_label_review_is_valid(payload.get("label_review"))
                    or (
                        version == 2
                        and not all(
                            isinstance(item, dict) and "suggestion_applicable" in item
                            for item in thread_decisions
                        )
                    )
                    or (
                        version in (3, 4, 5, 6, 7)
                        and (
                            not finding_publications_are_valid(
                                payload.get("finding_publications"), require_fixes=True
                            )
                            or not all(
                                isinstance(item, dict)
                                and {"fix_mode", "patch", "patch_path", "patch_sha256"} <= set(item)
                                for item in thread_decisions
                            )
                        )
                    )
                )
            )
            or (
                not legacy_plan and not all(isinstance(payload.get(key), list) for key in list_keys)
            )
            or (not legacy_plan and not isinstance(payload.get("presentation"), dict))
            or (final_plan and not review_chat_assessment_is_valid(payload.get("chat_assessment")))
            or (final_plan and payload.get("locale") not in {"en", "ru"})
            or not isinstance(payload["markdown"], str)
            or (not minimal_plan and payload["semver_impact"] == "unknown")
            or (not minimal_plan and not nonempty_string(payload["semver_rationale"]))
            or (
                not minimal_plan
                and not mr_metadata_assessment_is_valid(payload["mr_metadata_assessment"])
            )
            or (
                not minimal_plan
                and not review_publication_preview_is_valid(payload["publication_preview"])
            )
        )
        if invalid:
            raise WorkflowError("review plan payload is schema-invalid")
    elif kind in {"analysis_report", "critic_receipt"}:
        required_report = {
            "schema",
            "evidence_digest",
            "run_id",
            "session_id",
            "findings",
            "external_mutations",
        }
        payload_keys = set(payload)
        if kind == "critic_receipt":
            payload_keys -= {"contributors", "question_answers"}
        if payload_keys not in (
            required_report,
            required_report | {"scope_digest"},
            required_report | {"target_finding_ids"},
            required_report | {"scope_digest", "target_finding_ids"},
        ):
            raise WorkflowError(f"{kind} payload has unknown or missing fields")
        expected = "analysis-report" if kind == "analysis_report" else "critic-receipt"
        if (
            payload["schema"] != f"portable-gitlab/{expected}/v2"
            or not is_digest(payload["evidence_digest"])
            or not all(nonempty_string(payload[key]) for key in ("run_id", "session_id"))
            or not findings_are_valid(payload["findings"])
            or payload["external_mutations"] is not False
            or ("scope_digest" in payload and not is_digest(payload["scope_digest"]))
            or (
                "target_finding_ids" in payload
                and (
                    not isinstance(payload["target_finding_ids"], list)
                    or not all(nonempty_string(item) for item in payload["target_finding_ids"])
                )
            )
        ):
            raise WorkflowError(f"{kind} payload is schema-invalid")
        if kind == "critic_receipt":
            validate_critic(payload, cast("str", payload["evidence_digest"]))
    elif kind == "release_readiness":
        exact_keys(
            payload,
            {
                "schema",
                "evidence_digest",
                "verdict",
                "readiness",
                "gates",
                "external_mutations",
            },
            "release readiness payload",
        )
        gates = payload["gates"]
        if (
            payload["schema"] != "portable-gitlab/release-readiness/v2"
            or not is_digest(payload["evidence_digest"])
            or payload["verdict"] not in {"ready", "not_ready", "blocked"}
            or not isinstance(payload["readiness"], bool)
            or payload["external_mutations"] is not False
            or not isinstance(gates, dict)
            or set(gates) != {"semver", "compatibility", "migration", "rollback", "ci"}
            or not all(
                isinstance(gate, dict)
                and set(gate) == {"status", "evidence", "range"}
                and gate["status"] in {"passed", "failed", "blocked", "not_applicable"}
                and isinstance(gate["evidence"], list)
                and bool(gate["evidence"])
                and isinstance(gate["range"], dict)
                and set(gate["range"]) == {"base_sha", "start_sha", "head_sha"}
                and all(is_sha(gate["range"][key], nullable=True) for key in gate["range"])
                for gate in gates.values()
            )
        ):
            raise WorkflowError("release readiness payload is schema-invalid")
    elif kind == "finalize_report":
        allowed = {
            "status",
            "changed",
            "head_sha",
            "complete",
            "evidence_digest",
            "evidence_kind",
            "evidence_fingerprint_digest",
            "publication_plan_digest",
            "external_mutations",
            "release_readiness_digest",
            "release_readiness_valid",
        }
        if (
            not isinstance(payload, dict)
            or not set(payload).issubset(allowed)
            or not {
                "status",
                "changed",
                "complete",
                "evidence_digest",
                "evidence_kind",
                "evidence_fingerprint_digest",
                "external_mutations",
            }.issubset(payload)
        ):
            raise WorkflowError("finalize report payload has unknown or missing fields")
        if (
            payload["status"] not in {"ok", "stale", "not_applicable"}
            or not isinstance(payload["changed"], list)
            or not all(isinstance(item, str) for item in payload["changed"])
            or ("head_sha" in payload and not is_sha(payload["head_sha"], nullable=True))
            or not isinstance(payload["complete"], bool)
            or not is_digest(payload["evidence_digest"])
            or payload["evidence_kind"] != "evidence_snapshot"
            or not is_digest(payload["evidence_fingerprint_digest"])
            or (
                "publication_plan_digest" in payload
                and not is_digest(payload["publication_plan_digest"])
            )
            or payload["external_mutations"] is not False
            or (
                "release_readiness_digest" in payload
                and not is_digest(payload["release_readiness_digest"])
            )
            or (
                "release_readiness_valid" in payload
                and payload["release_readiness_valid"] is not True
            )
        ):
            raise WorkflowError("finalize report payload is schema-invalid")
    elif kind == "local_review_report":
        # The canonical schema above owns the structure; the reviewmatic
        # runtime owns verdict, continuity, and package-binding semantics.
        pass
    elif kind == "context_package":
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != "portable-gitlab/context-package/v2"
            or payload.get("mode") not in {"mr", "local"}
            or payload.get("external_mutations") is not False
            or not isinstance(payload.get("binding"), dict)
            or not is_digest(payload["binding"].get("evidence_digest"))
        ):
            raise WorkflowError("context package payload is schema-invalid")
        goal = payload.get("goal")
        acceptance = payload.get("acceptance_criteria")
        if (
            not isinstance(goal, dict)
            or not isinstance(acceptance, dict)
            or (goal.get("status") == "known" and not goal.get("text"))
            or (
                acceptance.get("status") == "known"
                and (not isinstance(acceptance.get("items"), list) or not acceptance["items"])
            )
        ):
            raise WorkflowError("context package goal or acceptance is schema-invalid")
    elif kind == "review_decision":
        required = {
            "schema",
            "evidence_digest",
            "finalize_digest",
            "mode",
            "external_mutations",
            "verdict",
            "run_id",
            "session_id",
            "findings",
            "unresolved_threads",
            "responses",
        }
        optional = {
            "context_digest",
            "critic_receipt_digest",
            "low_risk",
            "blocking_findings",
            "critic_findings",
            "accepted_findings",
            "critic_target_finding_ids",
            "blocking_finding_ids",
            "blocking_thread_ids",
            "owner_decision_reasons",
            "ci_job_assessments",
        }
        payload_keys = set(payload)
        if not required <= payload_keys or not payload_keys <= required | optional:
            raise WorkflowError("review decision payload has unknown or missing fields")
        responses = payload["responses"]
        if (
            payload["schema"] != "portable-gitlab/review-decision/v2"
            or not is_digest(payload["evidence_digest"])
            or not is_digest(payload["finalize_digest"])
            or ("context_digest" in payload and not is_digest(payload["context_digest"]))
            or (
                "critic_receipt_digest" in payload
                and payload["critic_receipt_digest"] is not None
                and not is_digest(payload["critic_receipt_digest"])
            )
            or payload["mode"] not in {"fast", "normal", "deep", "incremental", "unchanged"}
            or payload["verdict"] not in {"ready", "not_ready", "blocked"}
            or not all(nonempty_string(payload[key]) for key in ("run_id", "session_id"))
            or not findings_are_valid(payload["findings"])
            or (
                "critic_findings" in payload
                and not detailed_findings_are_valid(payload["critic_findings"])
            )
            or (
                "accepted_findings" in payload
                and not detailed_findings_are_valid(payload["accepted_findings"])
            )
            or (
                "critic_target_finding_ids" in payload
                and (
                    not isinstance(payload["critic_target_finding_ids"], list)
                    or not all(
                        nonempty_string(item) for item in payload["critic_target_finding_ids"]
                    )
                )
            )
            or (
                "blocking_finding_ids" in payload
                and (
                    not isinstance(payload["blocking_finding_ids"], list)
                    or not all(nonempty_string(item) for item in payload["blocking_finding_ids"])
                    or len(payload["blocking_finding_ids"])
                    != len(set(payload["blocking_finding_ids"]))
                )
            )
            or (
                "owner_decision_reasons" in payload
                and (
                    not isinstance(payload["owner_decision_reasons"], list)
                    or not all(nonempty_string(item) for item in payload["owner_decision_reasons"])
                )
            )
            or (
                "ci_job_assessments" in payload
                and (
                    not isinstance(payload["ci_job_assessments"], list)
                    or not all(
                        _ci_job_assessment_is_valid(item) for item in payload["ci_job_assessments"]
                    )
                )
            )
            or not findings_are_valid(payload["unresolved_threads"])
            or not isinstance(responses, list)
            or not all(_review_response_is_valid(item) for item in responses)
            or ("low_risk" in payload and not isinstance(payload["low_risk"], bool))
            or (
                "blocking_findings" in payload
                and not isinstance(payload["blocking_findings"], bool)
            )
            or ("external_mutations" in payload and payload["external_mutations"] is not False)
        ):
            raise WorkflowError("review decision payload is schema-invalid")
    else:
        raise WorkflowError("unknown artifact kind")


def allowed_endpoint(endpoint: str) -> bool:
    # These are the complete collection endpoints. Query values are generated, never caller input.
    if re.fullmatch(
        r"projects/[0-9]+/(?:releases|repository/tags)(?:\?[^#]+)?|projects/[0-9]+/repository/branches/[^/?#]+",
        endpoint,
    ):
        return True
    return bool(
        re.fullmatch(
            r"(?:user|projects/(?:[^/?]+|[0-9]+/(?:labels|milestones|pipelines|issues)(?:\?[^#]+)?|[0-9]+/pipelines/[1-9][0-9]*/(?:jobs|bridges)(?:\?[^#]+)?|[0-9]+/jobs/[1-9][0-9]*/trace|[0-9]+/(?:issues|merge_requests)/[1-9][0-9]*(?:/(?:approvals|closes_issues|discussions|changes|commits|links|notes|pipelines))?(?:\?[^#]+)?|[0-9]+/repository/tags/[^/?#]+|[0-9]+/repository/commits/[0-9a-fA-F]{1,128}/merge_requests(?:\?[^#]+)?|[0-9]+/repository/commits/[^/?#]+|[0-9]+/repository/(?:tree|files/[^/?#]+)\?[^#]+))",
            endpoint,
        )
    )


def glab_json(hostname: str, endpoint: str) -> object:
    if not re.fullmatch(r"[a-z0-9.-]+", hostname) or not allowed_endpoint(endpoint):
        raise WorkflowError("GitLab endpoint is outside the collection allowlist")
    glab = shutil.which("glab")
    if glab is None:
        raise WorkflowError("glab is unavailable; install and authenticate it outside this skill")
    try:
        completed = subprocess.run(
            [glab, "api", "--hostname", hostname, "--method", "GET", endpoint],
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkflowError("GitLab GET could not be completed") from exc
    if completed.returncode:
        raise WorkflowError(
            f"GitLab GET failed: {completed.stderr.strip() or completed.returncode}"
        )
    if len(completed.stdout.encode()) > MAX_BYTES:
        raise WorkflowError("GitLab response exceeds the size limit")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise WorkflowError("GitLab returned invalid JSON") from exc


def stop_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        with suppress(ProcessLookupError):
            process.kill()
    try:
        process.wait(timeout=PROCESS_CLEANUP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        with suppress(ProcessLookupError):
            process.kill()
        try:
            process.wait(timeout=PROCESS_CLEANUP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as exc:
            raise WorkflowError("GitLab job trace process could not be reaped") from exc


def trace_boundary(response: bytes | bytearray) -> tuple[int, int] | None:
    boundaries = [
        (position, len(separator))
        for separator in (b"\r\n\r\n", b"\n\n")
        if (position := response.find(separator)) >= 0
    ]
    if not boundaries:
        return None
    return min(boundaries, key=lambda boundary: boundary[0])


def split_glab_trace_response(response: bytes | bytearray) -> tuple[bytes, bytes] | None:
    boundary = trace_boundary(response)
    if boundary is None:
        return None
    position, length = boundary
    return bytes(response[:position]), bytes(response[position + length :])


def streamed_glab_trace(arguments: list[str]) -> tuple[bytes, bytes, bool]:
    if os.name != "posix" or not hasattr(os, "killpg"):
        raise WorkflowError("GitLab job trace streaming requires POSIX process capabilities")
    process: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    primary_error: BaseException | None = None
    stdout = bytearray()
    stderr = bytearray()
    tail_dropped = False
    deadline = time.monotonic() + TRACE_TIMEOUT_SECONDS
    try:
        process = subprocess.Popen(
            arguments,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        if process.stdout is None or process.stderr is None:
            raise WorkflowError("GitLab job trace streaming pipes are unavailable")
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, stdout)
        selector.register(process.stderr, selectors.EVENT_READ, stderr)
        stdout_limit = MAX_TRACE_HEADER_BYTES + MAX_HTTP_SEPARATOR_BYTES + MAX_TRACE_BYTES
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise WorkflowError("GitLab job trace request timed out")
            events = selector.select(remaining)
            if not events:
                raise WorkflowError("GitLab job trace request timed out")
            for key, _ in events:
                target = cast("bytearray", key.data)
                target_limit = stdout_limit if target is stdout else MAX_TRACE_HEADER_BYTES
                available = target_limit - len(target)
                chunk = os.read(key.fd, min(64 * 1024, available + 1))
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                target.extend(chunk)
                if len(stderr) > MAX_TRACE_HEADER_BYTES:
                    raise WorkflowError("GitLab job trace response exceeds the size limit")
                boundary = trace_boundary(stdout)
                if boundary is None:
                    if len(stdout) > MAX_TRACE_HEADER_BYTES:
                        raise WorkflowError(
                            "GitLab job trace response headers exceed the size limit"
                        )
                    continue
                position, length = boundary
                if position > MAX_TRACE_HEADER_BYTES:
                    raise WorkflowError("GitLab job trace response headers exceed the size limit")
                excess = len(stdout) - position - length - MAX_TRACE_BYTES
                if excess > 0:
                    del stdout[position + length : position + length + excess]
                    tail_dropped = True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise WorkflowError("GitLab job trace request timed out")
        try:
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired as exc:
            raise WorkflowError("GitLab job trace request timed out") from exc
        if returncode:
            raise WorkflowError(f"GitLab job trace request failed with status {returncode}")
        return bytes(stdout), bytes(stderr), tail_dropped
    except WorkflowError as exc:
        primary_error = exc
        raise
    except (OSError, ValueError, NotImplementedError) as exc:
        error = WorkflowError("GitLab job trace POSIX streaming is unavailable")
        primary_error = error
        raise error from exc
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        if selector is not None:
            with suppress(OSError, ValueError, NotImplementedError):
                selector.close()
        if process is not None:
            try:
                stop_process_group(process)
            except WorkflowError as cleanup_error:
                if primary_error is not None:
                    raise cleanup_error from primary_error
                raise


def parse_glab_trace(response: bytes, *, tail_dropped: bool = False) -> tuple[str, bool]:
    response_parts = split_glab_trace_response(response)
    if response_parts is None:
        raise WorkflowError("GitLab job trace response headers are unavailable")
    header_bytes, body = response_parts
    if len(header_bytes) > MAX_TRACE_HEADER_BYTES or len(body) > MAX_TRACE_BYTES:
        raise WorkflowError("GitLab job trace exceeds the response size limit")
    headers = header_bytes.decode("latin-1").splitlines()
    status_match = re.fullmatch(r"HTTP/\S+ ([0-9]{3})(?: .*)?", headers[0]) if headers else None
    if status_match is None:
        raise WorkflowError("GitLab job trace response status is unavailable")
    status = int(status_match.group(1))
    content_range = next(
        (
            line.split(":", 1)[1].strip()
            for line in headers[1:]
            if line.lower().startswith("content-range:")
        ),
        None,
    )
    complete = status == 200 and content_range is None and not tail_dropped
    if status in {200, 206} and content_range is not None:
        range_match = re.fullmatch(r"bytes ([0-9]+)-([0-9]+)/([0-9]+)", content_range)
        if range_match is not None:
            start, end, total = (int(item) for item in range_match.groups())
            complete = start == 0 and end + 1 == total and len(body) == total
    elif status not in {200, 206}:
        raise WorkflowError(f"GitLab job trace request returned HTTP {status}")
    return body.decode(errors="replace"), complete


def glab_text(hostname: str, endpoint: str) -> tuple[str, bool]:
    if not re.fullmatch(r"[a-z0-9.-]+", hostname) or not allowed_endpoint(endpoint):
        raise WorkflowError("GitLab endpoint is outside the collection allowlist")
    glab = shutil.which("glab")
    if glab is None:
        raise WorkflowError("glab is unavailable; install and authenticate it outside this skill")
    stdout, _stderr, tail_dropped = streamed_glab_trace(
        [
            glab,
            "api",
            "--hostname",
            hostname,
            "--method",
            "GET",
            "--include",
            "--header",
            f"Range: bytes=-{MAX_TRACE_BYTES}",
            endpoint,
        ]
    )
    return parse_glab_trace(stdout, tail_dropped=tail_dropped)


def paginated(hostname: str, endpoint: str, *, max_pages: int = MAX_PAGES) -> dict[str, object]:
    items: list[object] = []
    seen: set[str] = set()
    page_digests: set[str] = set()
    errors: list[str] = []
    for page in range(1, max_pages + 1):
        separator = "&" if "?" in endpoint else "?"
        try:
            value = glab_json(hostname, f"{endpoint}{separator}per_page=100&page={page}")
        except WorkflowError as exc:
            errors.append(str(exc))
            break
        if not isinstance(value, list):
            errors.append("GitLab pagination response is not an array")
            break
        page_digest = digest(value)
        if page_digest in page_digests:
            errors.append("GitLab pagination repeated a page")
            break
        page_digests.add(page_digest)
        for item in value:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if key not in seen:
                seen.add(key)
                items.append(item)
        # Issue-link listing is a whole-collection API, not a paged endpoint.
        # CE can return exactly 100 links while ignoring page/per_page entirely.
        if len(value) < 100 or re.fullmatch(
            r"projects/[^/]+/issues/[0-9]+/links", endpoint.split("?", maxsplit=1)[0]
        ):
            return {
                "items": items,
                "complete": True,
                "errors": [],
                "pages": page,
                "truncated": False,
            }
    if not errors:
        errors.append("pagination protective limit reached")
    return {
        "items": items,
        "complete": False,
        "errors": errors,
        "pages": max_pages if not errors else page,
        "truncated": True,
    }


def component(
    items: list[object] | None = None,
    *,
    complete: bool = True,
    errors: list[str] | None = None,
    pages: int = 0,
    truncated: bool = False,
) -> dict[str, object]:
    return {
        "items": items or [],
        "complete": complete,
        "errors": errors or [],
        "pages": pages,
        "truncated": truncated,
    }


def select_exact_pipeline(pipelines: dict[str, object], head_sha: str) -> dict[str, Any] | None:
    items = pipelines.get("items")
    if not isinstance(items, list):
        return None
    exact = [item for item in items if isinstance(item, dict) and item.get("sha") == head_sha]
    if not exact:
        return None

    def pipeline_id(item: dict[str, Any]) -> int:
        value = item.get("id")
        return value if isinstance(value, int) else -1

    return max(cast("list[dict[str, Any]]", exact), key=pipeline_id)


def trace_excerpt(value: str, source_complete: bool = True) -> dict[str, object]:
    sanitized = redact(re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)).replace("\r", "")
    encoded = sanitized.encode()
    truncated = not source_complete or len(encoded) > MAX_TRACE_BYTES
    if truncated:
        encoded = encoded[-MAX_TRACE_BYTES:]
        sanitized = encoded.decode(errors="replace")
    return {
        "complete": not truncated,
        "truncated": truncated,
        "excerpt": sanitized,
        "sha256": hashlib.sha256(value.encode()).hexdigest(),
    }


def pipeline_job(item: dict[str, Any], project_id: int, pipeline_id: int) -> dict[str, object]:
    fields = (
        "id",
        "name",
        "stage",
        "status",
        "allow_failure",
        "web_url",
        "created_at",
        "started_at",
        "finished_at",
        "duration",
        "queued_duration",
        "failure_reason",
    )
    return {
        "project_id": project_id,
        "pipeline_id": pipeline_id,
        **{key: item.get(key) for key in fields},
    }


def collect_pipeline_jobs(
    hostname: str, project_id: int, pipeline: dict[str, Any]
) -> dict[str, object]:
    pipeline_id = pipeline.get("id")
    if not isinstance(pipeline_id, int):
        return {
            "complete": False,
            "errors": ["selected pipeline has no numeric ID"],
            "pipelines": [],
            "truncated": True,
        }
    queue: list[tuple[int, int, int, int | None]] = [(project_id, pipeline_id, 0, None)]
    seen: set[tuple[int, int]] = set()
    collected: list[dict[str, object]] = []
    errors: list[str] = []
    traces = 0
    truncated = False
    while queue:
        current_project, current_pipeline, depth, parent_pipeline = queue.pop(0)
        identity = (current_project, current_pipeline)
        if identity in seen:
            continue
        if len(seen) >= MAX_CI_PIPELINES:
            errors.append("CI pipeline traversal limit reached")
            truncated = True
            break
        seen.add(identity)
        jobs = paginated(
            hostname,
            f"projects/{current_project}/pipelines/{current_pipeline}/jobs",
            max_pages=MAX_CI_JOB_PAGES,
        )
        bridges = paginated(
            hostname,
            f"projects/{current_project}/pipelines/{current_pipeline}/bridges",
            max_pages=MAX_CI_JOB_PAGES,
        )
        pipeline_errors = [
            *cast("list[str]", jobs["errors"]),
            *cast("list[str]", bridges["errors"]),
        ]
        normalized_jobs: list[dict[str, object]] = []
        for raw in [*cast("list[object]", jobs["items"]), *cast("list[object]", bridges["items"])]:
            if not isinstance(raw, dict) or not isinstance(raw.get("id"), int):
                pipeline_errors.append("GitLab returned invalid CI job metadata")
                continue
            normalized = pipeline_job(
                cast("dict[str, Any]", raw), current_project, current_pipeline
            )
            if raw.get("status") in {"failed", "canceled"}:
                if traces >= MAX_CI_TRACES:
                    traces += 1
                    normalized["trace"] = {
                        "complete": False,
                        "truncated": True,
                        "excerpt": "",
                        "sha256": None,
                    }
                    truncated = True
                else:
                    traces += 1
                    try:
                        trace, trace_complete = glab_text(
                            hostname, f"projects/{current_project}/jobs/{raw['id']}/trace"
                        )
                        normalized["trace"] = trace_excerpt(trace, trace_complete)
                    except WorkflowError as exc:
                        normalized["trace"] = {
                            "complete": False,
                            "truncated": True,
                            "excerpt": "",
                            "sha256": None,
                        }
                        pipeline_errors.append(str(exc))
            normalized_jobs.append(normalized)
        for raw in cast("list[object]", bridges["items"]):
            if not isinstance(raw, dict) or not isinstance(raw.get("downstream_pipeline"), dict):
                continue
            downstream = cast("dict[str, Any]", raw["downstream_pipeline"])
            downstream_id = downstream.get("id")
            downstream_project = downstream.get("project_id", current_project)
            if not isinstance(downstream_id, int) or not isinstance(downstream_project, int):
                pipeline_errors.append("downstream pipeline identity is incomplete")
                continue
            if depth >= MAX_PIPELINE_DEPTH:
                pipeline_errors.append("downstream pipeline depth limit reached")
                truncated = True
                continue
            queue.append((downstream_project, downstream_id, depth + 1, current_pipeline))
        collected.append(
            {
                "project_id": current_project,
                "pipeline_id": current_pipeline,
                "parent_pipeline_id": parent_pipeline,
                "depth": depth,
                "jobs": normalized_jobs,
                "complete": jobs["complete"] is True
                and bridges["complete"] is True
                and not pipeline_errors,
                "errors": pipeline_errors,
            }
        )
        errors.extend(pipeline_errors)
    return {
        "complete": not errors and not truncated,
        "errors": errors,
        "pipelines": collected,
        "truncated": truncated,
    }


def collect(
    target: dict[str, object], profile: str, *, persist: bool = True, locale: str = "en"
) -> dict[str, object]:
    if profile not in PROFILES:
        raise WorkflowError("workflow profile is unsafe")
    iid_value = target.get("iid")
    if not isinstance(iid_value, int):
        raise WorkflowError("GitLab target IID is invalid")
    hostname, project_path, kind, iid = (
        str(target["hostname"]),
        str(target["project_path"]),
        str(target["kind"]),
        iid_value,
    )
    project = glab_json(hostname, f"projects/{urlquote(project_path, safe='')}")
    if not isinstance(project, dict) or not isinstance(project.get("id"), int):
        raise WorkflowError("GitLab project identity is incomplete")
    project_id = project["id"]
    identity = {**target, "project_id": project_id}
    root = state_directory(profile, identity)
    labels = paginated(hostname, f"projects/{project_id}/labels?include_ancestor_groups=true")
    if kind == "new_issue":
        bundle: dict[str, object] = {
            "schema_version": ARTIFACT_VERSION,
            "profile": profile,
            "external_mutations": False,
            "target": identity,
            "project": {
                "id": project_id,
                "path": project_path,
                "path_with_namespace": project_path,
                "hostname": hostname,
            },
            "object": {},
            "labels": labels,
            "changed_files": component(),
            "commits": component(),
            "pipelines": component(),
            "discussions": component(),
            "head_sha": None,
            "base_sha": None,
            "start_sha": None,
            "artifact_root": str(root),
            "prepared_at": datetime.now(UTC).isoformat(),
            "components_complete": {
                "project": True,
                "labels": bool(labels["complete"]),
                "object": True,
                "changed_files": True,
                "commits": True,
                "pipelines": True,
                "discussions": True,
            },
        }
    else:
        object_value = glab_json(hostname, f"projects/{project_id}/{kind}/{iid}")
        if not isinstance(object_value, dict) or object_value.get("iid") not in {None, iid}:
            raise WorkflowError("GitLab target response is incomplete")
        discussions = paginated(hostname, f"projects/{project_id}/{kind}/{iid}/discussions")
        refs: dict[str, Any] = (
            cast("dict[str, Any]", object_value["diff_refs"])
            if isinstance(object_value.get("diff_refs"), dict)
            else {}
        )
        head_sha, base_sha, start_sha = (
            refs.get("head_sha"),
            refs.get("base_sha"),
            refs.get("start_sha"),
        )
        changed, commits, pipelines = component(), component(), component()
        if kind == "merge_requests":
            try:
                changes_value = glab_json(
                    hostname, f"projects/{project_id}/merge_requests/{iid}/changes"
                )
                overflow = isinstance(changes_value, dict) and (
                    changes_value.get("overflow") is True
                    or changes_value.get("changes_count") == "1000+"
                )
                if (
                    isinstance(changes_value, dict)
                    and isinstance(changes_value.get("changes"), list)
                    and not overflow
                    and changes_value.get("diff_refs") == refs
                ):
                    changed = component(cast("list[object]", changes_value["changes"]), pages=1)
                else:
                    changed = component(
                        complete=False,
                        errors=[
                            "GitLab changed-files response is incomplete, stale, or overflowed"
                        ],
                        pages=1,
                        truncated=True,
                    )
            except WorkflowError as exc:
                changed = component(complete=False, errors=[str(exc)], truncated=True)
            if not all(
                isinstance(value, str) and value for value in (base_sha, start_sha, head_sha)
            ):
                changed = component(
                    cast("list[object]", changed["items"]),
                    complete=False,
                    errors=[
                        *cast("list[str]", changed["errors"]),
                        "exact diff refs are unavailable",
                    ],
                    pages=cast("int", changed["pages"]),
                    truncated=True,
                )
            if isinstance(head_sha, str) and head_sha:
                commits = paginated(hostname, f"projects/{project_id}/merge_requests/{iid}/commits")
                if not any(
                    isinstance(commit, dict) and commit.get("id") == head_sha
                    for commit in cast("list[object]", commits["items"])
                ):
                    commits = component(
                        cast("list[object]", commits["items"]),
                        complete=False,
                        errors=[
                            *cast("list[str]", commits["errors"]),
                            "commits do not bind exact head SHA",
                        ],
                        pages=cast("int", commits["pages"]),
                        truncated=True,
                    )
                pipelines = paginated(
                    hostname,
                    (
                        f"projects/{project_id}/merge_requests/{iid}/pipelines"
                        if profile == "code-review"
                        else f"projects/{project_id}/pipelines?sha={urlquote(head_sha, safe='')}"
                    ),
                )
                if profile == "code-review" and pipelines["complete"] is True:
                    selected_pipeline = select_exact_pipeline(pipelines, head_sha)
                    if selected_pipeline is not None:
                        job_evidence = collect_pipeline_jobs(
                            hostname, project_id, selected_pipeline
                        )
                        selected_pipeline["job_evidence"] = job_evidence
                        if job_evidence["complete"] is not True:
                            pipelines = component(
                                cast("list[object]", pipelines["items"]),
                                complete=False,
                                errors=[
                                    *cast("list[str]", pipelines["errors"]),
                                    *cast("list[str]", job_evidence["errors"]),
                                ],
                                pages=cast("int", pipelines["pages"]),
                                truncated=bool(job_evidence["truncated"]),
                            )
            else:
                pipelines = component(
                    complete=False, errors=["exact head SHA is unavailable"], truncated=True
                )
                commits = component(
                    complete=False, errors=["exact head SHA is unavailable"], truncated=True
                )
        bundle = {
            "schema_version": ARTIFACT_VERSION,
            "profile": profile,
            "external_mutations": False,
            "target": identity,
            "project": {
                "id": project_id,
                "path": project_path,
                "path_with_namespace": project_path,
                "hostname": hostname,
            },
            "object": object_value,
            "labels": labels,
            "changed_files": changed,
            "commits": commits,
            "pipelines": pipelines,
            "discussions": discussions,
            "head_sha": head_sha,
            "base_sha": base_sha,
            "start_sha": start_sha,
            "artifact_root": str(root),
            "prepared_at": datetime.now(UTC).isoformat(),
            "components_complete": {
                "project": True,
                "labels": bool(labels["complete"]),
                "object": True,
                "changed_files": bool(changed["complete"]),
                "commits": bool(commits["complete"]),
                "pipelines": bool(pipelines["complete"]),
                "discussions": bool(discussions["complete"]),
            },
        }
    components_complete = cast("dict[str, bool]", bundle["components_complete"])
    if profile == "mr-prepare":
        from .mr_publication import collect_templates

        if locale not in {"en", "ru"}:
            raise WorkflowError("MR locale must be en or ru")
        cast("dict[str, Any]", bundle["project"]).update(
            {"locale": locale, "mr_templates": collect_templates(hostname, project)}
        )
    bundle["retrieval_complete"] = all(components_complete.values())
    if persist:
        artifact_path, artifact_digest = write_artifact(root, "evidence_snapshot", bundle)
        if profile not in {"mr-prepare", "release-prepare"}:
            write_json(
                root / "current.json",
                {"evidence_path": str(artifact_path), "evidence_digest": artifact_digest},
            )
        bundle["preview_artifact_path"], bundle["preview_digest"] = (
            str(artifact_path),
            artifact_digest,
        )
    return bundle


def evidence_from_root(
    root: Path, pointer_name: str = "current.json"
) -> tuple[Path, dict[str, Any]]:
    if pointer_name not in {"current.json", "review-evidence.json"}:
        raise WorkflowError("collection state pointer name is invalid")
    try:
        pointer = read_json(root / pointer_name, "collection state")
        path = pointer.get("evidence_path")
        if not isinstance(path, str):
            raise WorkflowError("collection state has no evidence snapshot")
        source = Path(path)
        if source.parent.parent.parent != root:
            raise WorkflowError("evidence snapshot escapes collection root")
        _, payload = artifact_payload(source, "evidence_snapshot")
        return source, payload
    except WorkflowError:
        if pointer_name != "current.json":
            raise
        # Legacy v1 state had one immutable bundle.json instead of a current pointer.
        source = root / "bundle.json"
        _, payload = artifact_payload(source, "evidence_snapshot")
        return source, payload


def marked_preview(label: str, value: str) -> str:
    separator = "" if value.endswith("\n") else "\n"
    return f"<!-- {label} START -->\n{value}{separator}<!-- {label} END -->"


def template_headings(body: str) -> list[str]:
    return re.findall(r"^#{1,6}\s+.+$", body, re.MULTILINE)


def pipeline_summary(bundle: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    pipelines = bundle.get("pipelines")
    head_sha = bundle.get("head_sha")
    if not isinstance(pipelines, dict) or pipelines.get("complete") is not True:
        return "unverified: collection incomplete", None
    if not isinstance(head_sha, str) or not head_sha:
        return "unverified: exact head SHA unavailable", None
    if not isinstance(pipelines.get("items"), list):
        return "unverified: pipeline data invalid", None
    pipeline = select_exact_pipeline(cast("dict[str, object]", pipelines), head_sha)
    if pipeline is None:
        return "missing", None
    raw_status = pipeline.get("status")
    if raw_status in {"success", "running", "failed", "canceled"}:
        return str(raw_status), pipeline
    if raw_status in {"created", "waiting_for_resource", "preparing", "pending"}:
        return "running", pipeline
    return f"unsupported raw state: {raw_status!s}", pipeline


def label_markdown_cell(value: object) -> str:
    if isinstance(value, list):
        value = ", ".join(str(item) for item in value) or "none"
    if value is None:
        value = "none"
    return str(value).replace("|", "\\|").replace("\n", " ")


def label_review_markdown(label_review: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "## Semantic label review",
        "",
        f"- Completeness: `{'complete' if label_review['complete'] else 'unresolved'}`",
        f"- Current: {label_markdown_cell(label_review['current'])}",
        f"- Proposed: {label_markdown_cell(label_review['proposed'])}",
        f"- Add: {label_markdown_cell(label_review['add'])}",
        f"- Remove: {label_markdown_cell(label_review['remove'])}",
        "",
        "| Semantic role | Intent | Current labels | Desired label | Action | Reason |",
        "|---|---|---|---|---|---|",
    ]
    for decision in label_review["decisions"]:
        lines.append(
            "| "
            + " | ".join(
                label_markdown_cell(decision[key])
                for key in ("role", "intent", "current", "desired_label", "action", "reason")
            )
            + " |"
        )
    if label_review["unresolved"]:
        lines.extend(
            [
                "",
                "Unresolved semantic intents:",
                *[f"- {value}" for value in label_review["unresolved"]],
            ]
        )
    lines.extend(
        [
            "",
            "This is a read-only delta. No label mutation command was generated or executed.",
        ]
    )
    return lines


def publication_markdown(
    bundle: dict[str, Any],
    content: dict[str, Any],
    inventory: dict[str, Any] | None = None,
    label_review: dict[str, Any] | None = None,
) -> str:
    target = bundle.get("target", {})
    profile = bundle.get("profile")
    if profile not in {"mr-prepare", "release-prepare"}:
        return (
            "\n".join(
                [
                    "# Verified publication plan",
                    "",
                    f"- Target: {target.get('url', 'local')}",
                    f"- Base SHA: {bundle.get('base_sha') or 'not applicable'}",
                    f"- Start SHA: {bundle.get('start_sha') or 'not applicable'}",
                    f"- Head SHA: {bundle.get('head_sha') or 'not applicable'}",
                    f"- Collection completeness: {'complete' if bundle.get('retrieval_complete') else 'partial'}",
                    "- `external_mutations=false`: this plan does not perform or propose automated publish/resolve/approve/merge operations.",
                    "",
                    "## Proposed text",
                    "",
                    f"### Title\n\n{content.get('title', '') or 'No changes.'}",
                    f"\n### Description\n\n{content.get('description', '') or 'No changes.'}",
                    "",
                    "Before manual publication, run `finalize`; stale or incomplete evidence blocks ready.",
                ]
            )
            + "\n"
        )
    object_value = bundle.get("object")
    if not isinstance(object_value, dict):
        raise WorkflowError("evidence object is invalid")
    if label_review is None:
        raise WorkflowError("publication plan requires a semantic label review")
    current_title = object_value.get("title")
    current_description = object_value.get("description")
    if not isinstance(current_title, str) or (
        current_description is not None and not isinstance(current_description, str)
    ):
        raise WorkflowError("current title or description is invalid")
    current_description = current_description or ""
    proposed_title = content["title"]
    proposed_description = content["description"]
    pipeline_status, pipeline = pipeline_summary(bundle)
    pipeline_id = pipeline.get("id") if pipeline is not None else None
    release_details: list[str] = []
    release_sections: list[str] = []
    if profile == "release-prepare":
        if inventory is None:
            raise WorkflowError("release publication plan requires an inventory")
        release_details = [
            f"- Release version: `v{content['version']}`",
            f"- Previous boundary: {inventory.get('previous_ref') or 'first release'}",
            f"- Previous SHA: {inventory.get('previous_sha') or 'not applicable'}",
            f"- Release range: `{inventory.get('revision_range')}`",
            f"- Inventory completeness: {'complete' if inventory.get('complete') else 'partial'}",
        ]
        release_sections = [
            "",
            "## Announcement",
            "",
            marked_preview("ANNOUNCEMENT", content["announcement"]),
            "",
            "## Illustration prompt",
            "",
            marked_preview("ILLUSTRATION PROMPT", content["illustration_prompt"]),
        ]
    return (
        "\n".join(
            [
                "# Verified publication plan",
                "",
                f"- Target: {target.get('url', 'local')}",
                f"- Base SHA: {bundle.get('base_sha') or 'not applicable'}",
                f"- Start SHA: {bundle.get('start_sha') or 'not applicable'}",
                f"- Head SHA: {bundle.get('head_sha') or 'not applicable'}",
                f"- Collection completeness: {'complete' if bundle.get('retrieval_complete') else 'partial'}",
                f"- Pipeline status for exact head SHA: `{pipeline_status}`",
                f"- Pipeline ID: {pipeline_id if pipeline_id is not None else 'not applicable'}",
                *release_details,
                "- `external_mutations=false`: this plan does not perform or propose automated publish/resolve/approve/merge operations.",
                "",
                "## Title",
                "",
                f"- Decision: `{'change' if current_title != proposed_title else 'keep'}`",
                "",
                "### Current title",
                "",
                marked_preview("CURRENT TITLE", current_title),
                "",
                "### Proposed title",
                "",
                marked_preview("PROPOSED TITLE", proposed_title),
                "",
                "## Description",
                "",
                f"- Decision: `{'change' if current_description != proposed_description else 'keep'}`",
                "",
                "### Current description",
                "",
                marked_preview("CURRENT DESCRIPTION", current_description),
                "",
                "### Proposed description",
                "",
                marked_preview("PROPOSED DESCRIPTION", proposed_description),
                *label_review_markdown(label_review),
                *release_sections,
                "",
                "Before manual publication, run `finalize` with the stable plan pointer and binding returned by scaffold; stale or incomplete evidence blocks readiness.",
            ]
        )
        + "\n"
    )


def release_asset(root: Path, role: str, suffix: str, content: str) -> dict[str, str]:
    content_digest = hashlib.sha256(content.encode()).hexdigest()
    name = f"{content_digest}-{role}.{suffix}"
    path = root / "artifacts" / "release_requests" / name
    return {
        "role": role,
        "name": name,
        "path": str(path),
        "sha256": content_digest,
        "content": content,
    }


def release_request_specs(
    root: Path,
    bundle: dict[str, Any],
    content: dict[str, Any],
    inventory: dict[str, Any],
    label_review: dict[str, Any],
    stage: str,
    post_merge_sha: str | None,
    complete: bool,
) -> list[dict[str, Any]]:
    target = cast("dict[str, Any]", bundle["target"])
    object_value = cast("dict[str, Any]", bundle["object"])
    repo = f"https://{target['hostname']}/{target['project_path']}"
    iid = str(target["iid"])
    hostname = cast("str", target["hostname"])
    project_id = cast("int", target["project_id"])
    description = release_asset(root, "description", "md", content["description"])
    requests: list[dict[str, Any]] = []

    def request(
        request_id: str,
        operation: str,
        command: list[str] | None,
        assets: list[dict[str, str]] | None = None,
    ) -> None:
        rendered_command = None
        if complete and command is not None:
            rendered_command = render_mutation_command(
                command,
                skill="release-prepare",
                action=f"{stage}:{request_id}",
                binding=digest(
                    {
                        "target": target,
                        "stage": stage,
                        "request_id": request_id,
                        "assets": [item["sha256"] for item in assets or []],
                        "argv": command,
                    }
                ),
                helper=Path(__file__).with_name("state_artifacts.py"),
            )
        requests.append(
            {
                "id": request_id,
                "stage": stage,
                "operation": operation,
                "command": rendered_command,
                "assets": assets or [],
            }
        )

    if stage == "pre_merge":
        announcement = release_asset(root, "announcement", "md", content["announcement"])
        prompt = release_asset(root, "illustration-prompt", "md", content["illustration_prompt"])
        request(
            "release-assets",
            "record immutable release assets",
            None,
            [description, announcement, prompt],
        )
        milestone_exists = any(
            isinstance(item, dict) and item.get("title") == content["milestone_title"]
            for item in inventory["milestone_candidates"]
        )
        if not milestone_exists:
            body = (
                json.dumps(
                    {"title": content["milestone_title"]}, ensure_ascii=False, sort_keys=True
                )
                + "\n"
            )
            asset = release_asset(root, "milestone", "json", body)
            request(
                "create-milestone",
                "create milestone",
                [
                    "glab",
                    "api",
                    "--hostname",
                    hostname,
                    "--method",
                    "POST",
                    f"projects/{project_id}/milestones",
                    "--silent",
                    "--header",
                    "Content-Type: application/json",
                    "--input",
                    asset["path"],
                ],
                [asset],
            )
        update = ["glab", "mr", "update", iid, "-R", repo]
        changed = False
        if object_value.get("title") != content["title"]:
            update.extend(("--title", content["title"]))
            changed = True
        if (object_value.get("description") or "") != content["description"]:
            update.extend(("--description-file", description["path"]))
            changed = True
        for label in label_review["add"]:
            update.extend(("--label", label))
            changed = True
        for label in label_review["remove"]:
            update.extend(("--unlabel", label))
            changed = True
        current_milestone = object_value.get("milestone")
        current_milestone_title = (
            current_milestone.get("title") if isinstance(current_milestone, dict) else None
        )
        if current_milestone_title != content["milestone_title"]:
            update.extend(("--milestone", content["milestone_title"]))
            changed = True
        if changed:
            update.append("--yes")
            request("update-release-mr", "update release merge request", update, [description])
        request(
            "publish-announcement",
            "publish announcement and attach illustration prompt",
            [
                "glab",
                "mr",
                "note",
                "create",
                iid,
                "-R",
                repo,
                "--resolvable=false",
                "--message",
                content["announcement"],
                "--attach",
                prompt["path"],
            ],
        )
        request(
            "merge-release-mr",
            "merge release merge request",
            [
                "glab",
                "mr",
                "merge",
                iid,
                "-R",
                repo,
                "--sha",
                cast("str", bundle["head_sha"]),
                "--yes",
                "--auto-merge=false",
            ],
        )
        return requests

    if stage != "post_merge" or not is_sha(post_merge_sha):
        raise WorkflowError("release publication stage or post-merge SHA is invalid")
    request(
        "create-release",
        "create release and close the milestone by default",
        [
            "glab",
            "release",
            "create",
            f"v{content['version']}",
            "--ref",
            cast("str", post_merge_sha),
            "--name",
            content["title"],
            "--notes-file",
            description["path"],
            "--milestone",
            content["milestone_title"],
            "--no-update",
            "-R",
            repo,
        ],
        [description],
    )
    for decision in content["work_items"]:
        identity = f"{decision['project_id']}-{decision['iid']}"
        if decision["action"] == "no_action":
            request(f"work-item-{identity}", "no action", None)
            continue
        payload = (
            {"state_event": "close"}
            if decision["action"] == "close"
            else {"body": decision["comment"]}
        )
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
        asset = release_asset(root, f"work-item-{identity}", "json", body)
        endpoint = f"projects/{decision['project_id']}/issues/{decision['iid']}"
        if decision["action"] == "comment":
            endpoint += "/notes"
        request(
            f"work-item-{identity}",
            f"{decision['action']} work item",
            [
                "glab",
                "api",
                "--hostname",
                hostname,
                "--method",
                "PUT" if decision["action"] == "close" else "POST",
                endpoint,
                "--silent",
                "--header",
                "Content-Type: application/json",
                "--input",
                asset["path"],
            ],
            [asset],
        )
    return requests


def write_release_request_assets(root: Path, requests: list[dict[str, Any]]) -> None:
    private_directory(root / "artifacts" / "release_requests")
    written: set[Path] = set()
    for request in requests:
        for asset in request["assets"]:
            path = Path(asset["path"])
            if path in written:
                continue
            write_companion(path, asset["content"])
            written.add(path)


def release_binding(
    evidence_digest: str,
    inventory_digest: str,
    content: dict[str, Any],
    requests: list[dict[str, Any]],
    stage: str,
    post_merge_sha: str | None,
    release_target_state: dict[str, Any] | None,
) -> str:
    bound_requests = [
        {**request, "command": command_without_execution_status(request.get("command"))}
        for request in requests
    ]
    return digest(
        {
            "evidence_digest": evidence_digest,
            "inventory_digest": inventory_digest,
            "release_content": content,
            "requests": bound_requests,
            "stage": stage,
            "post_merge_sha": post_merge_sha,
            "release_target_state": release_target_state,
        }
    )


def collect_release_target_state(
    hostname: str, project_id: int, tag_name: str, post_merge_sha: str
) -> dict[str, object]:
    encoded_tag = urlquote(tag_name, safe="")
    tags = paginated(hostname, f"projects/{project_id}/repository/tags?search={encoded_tag}")
    releases = paginated(hostname, f"projects/{project_id}/releases?search={encoded_tag}")
    if tags.get("complete") is not True or releases.get("complete") is not True:
        raise WorkflowError("existing release tag or release could not be checked completely")
    exact_tags = [
        item
        for item in cast("list[object]", tags.get("items", []))
        if isinstance(item, dict) and item.get("name") == tag_name
    ]
    exact_releases = [
        item
        for item in cast("list[object]", releases.get("items", []))
        if isinstance(item, dict) and item.get("tag_name") == tag_name
    ]
    if len(exact_tags) > 1 or len(exact_releases) > 1:
        raise WorkflowError("existing release tag or release identity is ambiguous")
    tag_sha: str | None = None
    if exact_tags:
        commit = exact_tags[0].get("commit")
        if not isinstance(commit, dict) or not is_sha(commit.get("id")):
            raise WorkflowError("existing release tag has no exact commit SHA")
        tag_sha = cast("str", commit["id"])
        if tag_sha != post_merge_sha:
            raise WorkflowError("existing release tag points to a different commit")
    if exact_releases:
        raise WorkflowError("GitLab Release already exists for the selected version")
    return {
        "tag_name": tag_name,
        "tag_exists": bool(exact_tags),
        "tag_sha": tag_sha,
        "release_exists": False,
    }


def release_publication_markdown(
    root: Path,
    bundle: dict[str, Any],
    inventory: dict[str, Any],
    content: dict[str, Any],
    requests: list[dict[str, Any]],
    stage: str,
    post_merge_sha: str | None,
    binding: str,
    complete: bool,
) -> str:
    runner = Path(sys.argv[0]).resolve()
    pointer = root / "release-publication.json"
    finalize_command = shlex.join(
        [
            sys.executable,
            str(runner),
            "finalize",
            "--plan",
            str(pointer),
            "--expected-binding",
            binding,
        ]
    )
    lines = [
        "# Verified release publication plan",
        "",
        f"- Stage: `{stage}`",
        "- Stages: `pre_merge` then `post_merge`",
        f"- Target: {bundle['target']['url']}",
        f"- Original head SHA: `{inventory['head_sha']}`",
        f"- Post-merge SHA: `{post_merge_sha or 'not available'}`",
        f"- Release: `v{content['version']}`",
        f"- Milestone: {content['milestone_title']}",
        f"- Contributors: {', '.join(content['contributors']) or 'none'}",
        f"- Reviewers: {', '.join(content['reviewers']) or 'none'}",
        f"- Illustration preset: `{content['illustration_style']['preset']}`",
        f"- Illustration reference: {content['illustration_style']['reference'] or 'none'}",
        f"- Illustration custom direction: {content['illustration_style']['custom'] or 'none'}",
        "- `external_mutations=false` means every shown command is manual only; this helper never executes it.",
        "",
        "## Release content",
        "",
        f"### Title\n\n{content['title']}",
        f"\n### Description\n\n{content['description']}",
        f"\n### Announcement\n\n{content['announcement']}",
        f"\n### Illustration prompt\n\n{content['illustration_prompt']}",
        "",
        "## Work-item decisions",
        "",
    ]
    for decision in content["work_items"]:
        uncertainty = "uncertain" if decision["uncertain"] else "certain"
        lines.append(
            f"- `{decision['project_id']}#{decision['iid']}`: `{decision['action']}`; "
            f"{uncertainty}; {decision['rationale']}"
        )
    lines.extend(["", "## Finalize this stage", ""])
    if complete:
        lines.extend(["```sh", finalize_command, "```"])
    else:
        lines.append("Commands are withheld because the plan is incomplete.")
    lines.extend(["", f"## {stage.replace('_', '-')} commands", ""])
    if stage == "pre_merge":
        lines.extend(
            [
                "The announcement attachment is not deduplicated by glab. Inspect the target discussion before choosing to repeat that command.",
                "",
            ]
        )
    for request in requests:
        lines.append(f"### {request['operation']}")
        if request["id"].startswith("work-item-"):
            identity = request["id"].removeprefix("work-item-")
            project_id, iid = (int(value) for value in identity.split("-", 1))
            decision = next(
                item
                for item in content["work_items"]
                if item["project_id"] == project_id and item["iid"] == iid
            )
            lines.extend(
                [
                    "",
                    f"Rationale: {decision['rationale']}",
                    f"Uncertain: `{'true' if decision['uncertain'] else 'false'}`",
                ]
            )
        if request["command"] is not None:
            lines.extend(["", "```sh", request["command"], "```"])
        else:
            lines.extend(["", "No command."])
        lines.append("")
    if stage == "pre_merge" and complete:
        transition = shlex.join(
            [
                sys.executable,
                str(runner),
                "post-merge",
                "--plan",
                str(pointer),
                "--expected-binding",
                binding,
            ]
        )
        lines.extend(
            [
                "## Post-merge transition",
                "",
                "After the manual merge command succeeds, collect the merged state and replace this plan:",
                "",
                "```sh",
                transition,
                "```",
                "",
            ]
        )
    if stage == "post_merge":
        lines.extend(
            [
                "Creating the release closes the selected milestone by default.",
                "Finalize this post-merge plan before running any post-merge command.",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def publish_stable_release(
    root: Path, plan_path: Path, plan_digest: str, binding: str, markdown: str
) -> tuple[Path, Path]:
    stable_markdown = root / "release-publication.md"
    stable_plan = root / "release-publication.json"
    lock = root / ".release-publication.lock"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise WorkflowError("another release publication update holds the lock") from exc
    destinations = [stable_markdown, stable_plan]
    try:
        if any(item.is_symlink() for item in destinations):
            raise WorkflowError("stable release publication paths must not be symlinks")
        previous = [item.read_bytes() if item.exists() else None for item in destinations]
        try:
            write_bytes(stable_markdown, versioned_markdown(stable_markdown, markdown.encode()))
            write_json(
                stable_plan,
                {
                    "plan_path": str(plan_path),
                    "digest": plan_digest,
                    "binding": binding,
                },
            )
        except BaseException:
            for destination, old in zip(destinations, previous, strict=True):
                if old is None:
                    destination.unlink(missing_ok=True)
                else:
                    write_bytes(destination, old)
            raise
    finally:
        lock.rmdir()
    return stable_plan, stable_markdown


def scaffold(
    bundle_file: str,
    content_file: str,
    plan_name: str,
    inventory_file: str | None = None,
) -> dict[str, object]:
    source = regular_file(Path(bundle_file), "evidence snapshot")
    _, bundle = artifact_payload(source, "evidence_snapshot")
    root = artifact_root(Path(str(bundle["artifact_root"])))
    evidence_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    expected_source = root / "artifacts" / "evidence_snapshot" / f"{evidence_digest}.json"
    if source != expected_source:
        raise WorkflowError("evidence snapshot is not in its content-addressed collection")
    profile = bundle.get("profile")
    if profile == "mr-prepare":
        from .mr_publication import scaffold as scaffold_mr

        return scaffold_mr(source, bundle, read_json(Path(content_file), "MR content"))
    if profile == "release-prepare":
        if inventory_file is None:
            raise WorkflowError("release publication plan requires --inventory")
        inventory_module = importlib.import_module("release_inventory")
        _, release_inventory, inventory_digest = inventory_module.validate_inventory_binding(
            inventory_file, source
        )
        content = read_json(Path(content_file), "release content")
        if not release_content_is_valid(content, release_inventory):
            raise WorkflowError(
                "release content is invalid or contains choices outside the exact inventory"
            )
        release_label_intent = cast("dict[str, str | None]", content["label_intent"])
        if release_label_intent["change_type"] != "release" or release_label_intent[
            "compatibility"
        ] not in {"major", "minor", "patch"}:
            raise WorkflowError("release content requires release and compatibility label intent")
        label_review = review_labels(bundle, release_label_intent)
        complete = (
            bundle.get("retrieval_complete") is True
            and release_inventory.get("complete") is True
            and label_review.get("complete") is True
            and cast("dict[str, Any]", bundle.get("object", {})).get("state") == "opened"
        )
        requests = release_request_specs(
            root, bundle, content, release_inventory, label_review, "pre_merge", None, complete
        )
        write_release_request_assets(root, requests)
        binding = release_binding(
            evidence_digest, inventory_digest, content, requests, "pre_merge", None, None
        )
        markdown = release_publication_markdown(
            root,
            bundle,
            release_inventory,
            content,
            requests,
            "pre_merge",
            None,
            binding,
            complete,
        )
        release_companions = [
            {
                "name": f"release-{role}-v{content['version']}.md",
                "content": value,
                "sha256": hashlib.sha256(value.encode()).hexdigest(),
            }
            for role, value in (
                ("description", content["description"]),
                ("announcement", content["announcement"]),
                ("illustration-prompt", content["illustration_prompt"]),
            )
        ]
        payload = {
            "profile": "release-prepare",
            "external_mutations": False,
            "target": bundle["target"],
            "evidence_digest": evidence_digest,
            "complete": complete,
            "markdown": markdown,
            "plan_name": Path(plan_name).name,
            "inventory_digest": inventory_digest,
            "release_version": content["version"],
            "companions": release_companions,
            "label_review": label_review,
            "stage": "pre_merge",
            "release_content": content,
            "requests": requests,
            "post_merge_sha": None,
            "release_target_state": None,
        }
        path, plan_digest = write_artifact(root, "publication_plan", payload)
        markdown_path, markdown_digest = write_companion(path.with_suffix(".md"), markdown)
        companion_outputs: list[dict[str, str]] = []
        for companion in release_companions:
            companion_path, companion_digest = write_companion(
                path.with_name(f"{plan_digest}-{companion['name']}"), companion["content"]
            )
            companion_outputs.append(
                {
                    "name": companion["name"],
                    "path": str(companion_path),
                    "digest": companion_digest,
                }
            )
        stable_plan_path: Path | None = None
        stable_markdown_path: Path | None = None
        if complete:
            stable_plan_path, stable_markdown_path = publish_stable_release(
                root, path, plan_digest, binding, markdown
            )
        return {
            "status": "ok" if complete else "incomplete",
            "summary": {
                "tldr": "Prepared a local Markdown plan for manual release publication.",
                "scope": [str(bundle.get("target", {}).get("url", "local"))],
                "risks": [] if complete else ["collection, inventory, or label intent incomplete"],
                "checks": ["schema-valid evidence", "exact release inventory", "semantic binding"],
            },
            "artifact_path": str(path),
            "digest": plan_digest,
            "plan_path": str(stable_plan_path) if stable_plan_path is not None else None,
            "binding": binding,
            "markdown_path": str(stable_markdown_path)
            if stable_markdown_path is not None
            else None,
            "immutable_markdown_path": str(markdown_path),
            "markdown_digest": markdown_digest,
            "companions": companion_outputs,
            "requests": requests,
            "external_mutations": False,
        }
    content_value = exact_keys(
        read_json(Path(content_file), "content"), {"title", "description"}, "content"
    )
    if not nonempty_string(content_value["title"]) or not isinstance(
        content_value["description"], str
    ):
        raise WorkflowError("content requires a non-empty title and a description string")
    content = content_value
    markdown = publication_markdown(bundle, content)
    complete = bool(bundle.get("retrieval_complete"))
    generic_payload: dict[str, Any] = {
        "profile": bundle.get("profile"),
        "external_mutations": False,
        "target": bundle.get("target"),
        "evidence_digest": evidence_digest,
        "complete": complete,
        "markdown": markdown,
        "plan_name": Path(plan_name).name,
    }
    path, plan_digest = write_artifact(root, "publication_plan", generic_payload)
    markdown_path, markdown_digest = write_companion(path.with_suffix(".md"), markdown)
    return {
        "status": "ok" if complete else "incomplete",
        "summary": {
            "tldr": "Prepared a local Markdown plan for manual publication.",
            "scope": [str(bundle.get("target", {}).get("url", "local"))],
            "risks": [] if complete else ["collection, inventory, or label intent incomplete"],
            "checks": [
                "schema-valid evidence",
                "content-addressed publication plan",
            ],
        },
        "artifact_path": str(path),
        "digest": plan_digest,
        "plan_path": None,
        "binding": None,
        "markdown_path": None,
        "immutable_markdown_path": str(markdown_path),
        "markdown_digest": markdown_digest,
        "companions": [],
        "external_mutations": False,
    }


def fingerprint(bundle: dict[str, Any]) -> dict[str, object]:
    return {
        **({"mr_project": bundle.get("project")} if bundle.get("profile") == "mr-prepare" else {}),
        "target": bundle.get("target"),
        "head_sha": bundle.get("head_sha"),
        "base_sha": bundle.get("base_sha"),
        "start_sha": bundle.get("start_sha"),
        "object": bundle.get("object"),
        "labels": bundle.get("labels"),
        "discussions": bundle.get("discussions"),
        "changed_files": bundle.get("changed_files"),
        "commits": bundle.get("commits"),
        "pipelines": bundle.get("pipelines"),
        "retrieval_complete": bundle.get("retrieval_complete"),
    }


def finalize(root_value: str, pointer_name: str = "current.json") -> dict[str, object]:
    root = artifact_root(Path(root_value))
    source, baseline = evidence_from_root(root, pointer_name)
    target = baseline.get("target")
    if not isinstance(target, dict):
        raise WorkflowError("evidence target is missing")
    if target.get("kind") == "new_issue":
        return {
            "status": "not_applicable",
            "changed": [],
            "complete": baseline.get("retrieval_complete"),
            "evidence_digest": hashlib.sha256(source.read_bytes()).hexdigest(),
        }
    current = collect(target, str(baseline.get("profile", "task-triage")), persist=False)
    before, after = fingerprint(baseline), fingerprint(current)
    changed = [name for name in before if before[name] != after[name]]
    return {
        "status": "ok" if not changed and bool(current.get("retrieval_complete")) else "stale",
        "changed": changed,
        "head_sha": current.get("head_sha"),
        "complete": current.get("retrieval_complete"),
        "evidence_digest": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def resolve_release_plan(path: Path) -> Path:
    pointer_path = regular_file(path, "release publication pointer")
    pointer = read_json(pointer_path, "release publication pointer")
    pointer_digest = pointer.get("digest")
    if not is_digest(pointer_digest) or not is_digest(pointer.get("binding")):
        raise WorkflowError("release publication pointer is invalid")
    expected = pointer_path.parent / "artifacts" / "publication_plan" / f"{pointer_digest}.json"
    if pointer.get("plan_path") != str(expected):
        raise WorkflowError("release publication pointer escapes its collection")
    return expected


def plan_context(
    plan_value: str,
) -> tuple[Path, Path, dict[str, Any], str, Path, dict[str, Any], dict[str, Any] | None]:
    candidate = Path(plan_value)
    if candidate.name == "mr-publication.json":
        from .mr_publication import resolve_plan

        candidate = resolve_plan(candidate)
    elif candidate.name == "release-publication.json":
        candidate = resolve_release_plan(candidate)
    plan_path = regular_file(candidate, "publication plan")
    _, plan = artifact_payload(plan_path, "publication_plan")
    plan_digest = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    if plan_path.parent.name != "publication_plan" or plan_path.parent.parent.name != "artifacts":
        raise WorkflowError("publication plan path is outside a collection")
    root = artifact_root(plan_path.parent.parent.parent)
    expected_plan = root / "artifacts" / "publication_plan" / f"{plan_digest}.json"
    if plan_path != expected_plan:
        raise WorkflowError("publication plan is not in its content-addressed collection")
    markdown = plan.get("markdown")
    if not isinstance(markdown, str):
        raise WorkflowError("publication plan Markdown is invalid")
    markdown_path = regular_file(plan_path.with_suffix(".md"), "Markdown companion")
    if markdown_path.read_bytes() != markdown.encode():
        raise WorkflowError("Markdown companion does not match the publication plan")
    evidence_digest = plan.get("evidence_digest")
    if not is_digest(evidence_digest):
        raise WorkflowError("publication plan evidence digest is invalid")
    source = regular_file(
        root / "artifacts" / "evidence_snapshot" / f"{evidence_digest}.json",
        "evidence snapshot",
    )
    if hashlib.sha256(source.read_bytes()).hexdigest() != evidence_digest:
        raise WorkflowError("evidence snapshot does not match the publication plan")
    _, baseline = artifact_payload(source, "evidence_snapshot")
    release_inventory: dict[str, Any] | None = None
    expected_complete = baseline.get("retrieval_complete")
    label_review = plan.get("label_review")
    if label_review is not None:
        validator = (
            code_review_label_review_is_valid if "mr_content" in plan else label_review_is_valid
        )
        if not validator(label_review):
            raise WorkflowError("publication plan label review is invalid")
        expected_complete = bool(expected_complete) and label_review.get("complete") is True
    if plan.get("profile") == "mr-prepare":
        from .mr_publication import resolve_plan, validate_plan

        if "mr_content" not in plan:
            raise WorkflowError("legacy MR plan: prepare and scaffold the MR again")
        if resolve_plan(root / "mr-publication.json") != plan_path:
            raise WorkflowError("MR plan was superseded; prepare again")
        validate_plan(root, plan, baseline)
    if plan.get("profile") == "release-prepare":
        pointer = read_json(
            regular_file(root / "release-publication.json", "release publication pointer"),
            "release publication pointer",
        )
        if pointer.get("plan_path") != str(plan_path) or pointer.get("digest") != plan_digest:
            raise WorkflowError("release plan was superseded; prepare again")
        stable_markdown = regular_file(
            root / "release-publication.md", "stable release publication"
        )
        if markdown_body(stable_markdown) != markdown.encode():
            raise WorkflowError(
                "stable release publication does not match this plan; prepare again"
            )
        inventory_digest = plan.get("inventory_digest")
        if not is_digest(inventory_digest):
            raise WorkflowError("release publication plan inventory digest is invalid")
        inventory_module = importlib.import_module("release_inventory")
        inventory_path = root / "artifacts" / "release_inventory" / f"{inventory_digest}.json"
        _, release_inventory, actual_inventory_digest = inventory_module.validate_inventory_binding(
            inventory_path, source
        )
        if actual_inventory_digest != inventory_digest:
            raise WorkflowError("release inventory does not match the publication plan")
        release_content = plan.get("release_content")
        if not release_content_is_valid(release_content, release_inventory):
            raise WorkflowError("release publication content does not match the inventory")
        expected_complete = bool(expected_complete) and release_inventory.get("complete") is True
        companions = plan.get("companions")
        if not companions_are_valid(companions):
            raise WorkflowError("release publication companions are invalid")
        for companion in cast("list[dict[str, str]]", companions):
            companion_path = regular_file(
                plan_path.with_name(f"{plan_digest}-{companion['name']}"),
                "release publication companion",
            )
            if (
                companion_path.read_bytes() != companion["content"].encode()
                or hashlib.sha256(companion_path.read_bytes()).hexdigest() != companion["sha256"]
            ):
                raise WorkflowError("release publication companion does not match the plan")
        requests = plan.get("requests")
        if not release_requests_are_valid(requests):
            raise WorkflowError("release publication requests are invalid")
        typed_requests = cast("list[dict[str, Any]]", requests)
        expected_requests = release_request_specs(
            root,
            baseline,
            cast("dict[str, Any]", release_content),
            release_inventory,
            cast("dict[str, Any]", label_review),
            plan["stage"],
            plan["post_merge_sha"],
            plan["complete"],
        )
        comparable_requests = [
            {**request, "command": command_without_execution_status(request.get("command"))}
            for request in typed_requests
        ]
        comparable_expected = [
            {**request, "command": command_without_execution_status(request.get("command"))}
            for request in expected_requests
        ]
        if comparable_requests != comparable_expected:
            raise WorkflowError("release publication requests do not match the bound evidence")
        for request in typed_requests:
            for asset in request["assets"]:
                asset_path = regular_file(Path(asset["path"]), "release request asset")
                expected_asset = root / "artifacts" / "release_requests" / asset["name"]
                if (
                    asset_path != expected_asset
                    or asset_path.read_bytes() != asset["content"].encode()
                    or hashlib.sha256(asset_path.read_bytes()).hexdigest() != asset["sha256"]
                ):
                    raise WorkflowError("release request asset does not match the plan")
        actual_binding = release_binding(
            plan["evidence_digest"],
            inventory_digest,
            cast("dict[str, Any]", release_content),
            typed_requests,
            plan["stage"],
            plan["post_merge_sha"],
            plan["release_target_state"],
        )
        if pointer.get("binding") != actual_binding:
            raise WorkflowError("release publication pointer binding is invalid")
    if (
        plan.get("profile") != baseline.get("profile")
        or plan.get("target") != baseline.get("target")
        or plan.get("complete") != expected_complete
    ):
        raise WorkflowError("publication plan does not bind its evidence identity")
    return root, plan_path, plan, plan_digest, source, baseline, release_inventory


def finalize_plan(
    plan_value: str,
    expected_binding: str | None = None,
) -> tuple[dict[str, object], Path, Path, dict[str, Any]]:
    root, _, plan, plan_digest, source, baseline, release_inventory = plan_context(plan_value)
    if expected_binding is not None:
        if not is_digest(expected_binding):
            raise WorkflowError("expected publication plan binding is invalid")
        if plan.get("profile") == "mr-prepare":
            from .mr_publication import plan_binding

            actual_binding = plan_binding(
                plan["evidence_digest"], plan["mr_content"], plan["requests"]
            )
        elif plan.get("profile") == "release-prepare":
            actual_binding = release_binding(
                plan["evidence_digest"],
                plan["inventory_digest"],
                plan["release_content"],
                plan["requests"],
                plan["stage"],
                plan["post_merge_sha"],
                plan["release_target_state"],
            )
        else:
            raise WorkflowError("publication plan binding is not supported")
        if actual_binding != expected_binding:
            raise WorkflowError("publication plan binding is stale; prepare again")
    target = baseline.get("target")
    if not isinstance(target, dict):
        raise WorkflowError("evidence target is missing")
    if target.get("kind") == "new_issue":
        return (
            {
                "status": "not_applicable",
                "changed": [],
                "complete": baseline.get("retrieval_complete"),
                "publication_plan_digest": plan_digest,
            },
            root,
            source,
            baseline,
        )
    current = collect(
        target,
        str(baseline.get("profile", "task-triage")),
        persist=False,
        locale=baseline.get("project", {}).get("locale", "en"),
    )
    before, after = fingerprint(baseline), fingerprint(current)
    changed = [name for name in before if before[name] != after[name]]
    plan_label_review = plan.get("label_review")
    complete = bool(current.get("retrieval_complete")) and (
        plan_label_review is None or plan_label_review.get("complete") is True
    )
    if release_inventory is not None:
        inventory_module = importlib.import_module("release_inventory")
        current_inventory = inventory_module.refresh_inventory(release_inventory, source)
        if inventory_module.inventory_fingerprint(
            release_inventory
        ) != inventory_module.inventory_fingerprint(current_inventory):
            changed.append("release_inventory")
        complete = complete and current_inventory.get("complete") is True
        if plan.get("stage") == "post_merge":
            project = baseline.get("project")
            if not isinstance(project, dict):
                raise WorkflowError("post-merge release project identity is unavailable")
            current_release_target = collect_release_target_state(
                cast("str", project["hostname"]),
                cast("int", project["id"]),
                f"v{plan['release_content']['version']}",
                cast("str", plan["post_merge_sha"]),
            )
            if current_release_target != plan.get("release_target_state"):
                changed.append("release_target_state")
    if plan.get("profile") == "mr-prepare":
        # A concurrent successful scaffold must not let an older check report readiness.
        plan_context(plan_value)
        from .mr_publication import resolve_plan

        if resolve_plan(root / "mr-publication.json").stem != plan_digest:
            raise WorkflowError("MR plan was superseded during the freshness check")
    if plan.get("profile") == "release-prepare":
        # Recheck the stable pointer after remote collection for the same reason.
        _, _, _, current_digest, _, _, _ = plan_context(plan_value)
        if current_digest != plan_digest:
            raise WorkflowError("release plan was superseded during the freshness check")
    return (
        {
            "status": "ok" if not changed and complete else "stale",
            "changed": changed,
            "head_sha": current.get("head_sha"),
            "complete": complete,
            "publication_plan_digest": plan_digest,
        },
        root,
        source,
        baseline,
    )


def release_inventory_semantics(value: dict[str, Any]) -> dict[str, Any]:
    result = {
        key: item
        for key, item in value.items()
        if key
        not in {
            "evidence_digest",
            "artifact_root",
            "prepared_at",
            "milestone_candidates",
        }
    }
    counts = result.get("counts")
    if isinstance(counts, dict):
        result["counts"] = {
            key: item for key, item in counts.items() if key != "milestone_candidates"
        }
    return result


def post_merge_plan(
    plan_value: str, expected_binding: str, content_file: str | None = None
) -> dict[str, object]:
    root, _, plan, _, _, baseline, inventory = plan_context(plan_value)
    if plan.get("profile") != "release-prepare" or plan.get("stage") not in {
        "pre_merge",
        "post_merge",
    }:
        raise WorkflowError("post-merge requires the current release plan")
    if not is_digest(expected_binding):
        raise WorkflowError("expected publication plan binding is invalid")
    actual_binding = release_binding(
        plan["evidence_digest"],
        plan["inventory_digest"],
        plan["release_content"],
        plan["requests"],
        plan["stage"],
        plan["post_merge_sha"],
        plan["release_target_state"],
    )
    if actual_binding != expected_binding:
        raise WorkflowError("publication plan binding is stale; prepare again")
    if inventory is None:
        raise WorkflowError("release inventory is unavailable")
    target = baseline.get("target")
    if not isinstance(target, dict):
        raise WorkflowError("release evidence target is missing")
    current = collect(target, "release-prepare", persist=False)
    current_object = current.get("object")
    original_head = baseline.get("head_sha")
    if (
        current.get("retrieval_complete") is not True
        or not isinstance(current_object, dict)
        or current_object.get("state") != "merged"
        or not nonempty_string(current_object.get("merged_at"))
        or current.get("head_sha") != original_head
    ):
        raise WorkflowError(
            "release merge request is not completely merged at the approved original head"
        )
    evidence_path, evidence_digest = write_artifact(root, "evidence_snapshot", current)
    inventory_module = importlib.import_module("release_inventory")
    previous_ref = inventory.get("previous_ref") if inventory.get("previous_ref_explicit") else None
    current_inventory = inventory_module.collect_inventory(
        current,
        evidence_digest,
        inventory["repo_root"],
        previous_ref,
        inventory_module.DEFAULT_WORKERS,
    )
    inventory_changed = release_inventory_semantics(inventory) != release_inventory_semantics(
        current_inventory
    )
    if inventory_changed and content_file is None:
        raise WorkflowError(
            "release inventory changed after approval; provide refreshed approved --content"
        )
    inventory_path, inventory_digest = write_artifact(root, "release_inventory", current_inventory)
    post_merge_sha = next(
        (
            value
            for value in (
                current_object.get("merge_commit_sha"),
                current_object.get("squash_commit_sha"),
                original_head,
            )
            if is_sha(value)
        ),
        None,
    )
    if not isinstance(post_merge_sha, str):
        raise WorkflowError("merged release has no exact publication SHA")
    content = (
        read_json(Path(content_file), "refreshed release content")
        if content_file is not None
        else cast("dict[str, Any]", plan["release_content"])
    )
    if not release_content_is_valid(content, current_inventory):
        raise WorkflowError("post-merge release content does not match the refreshed inventory")
    previous_content = cast("dict[str, Any]", plan["release_content"])
    refreshable_fields = {"contributors", "reviewers", "work_items"}
    if any(
        content[key] != previous_content[key] for key in content if key not in refreshable_fields
    ):
        raise WorkflowError(
            "post-merge refreshed content may change only contributors, reviewers, and work_items"
        )
    label_review = cast("dict[str, Any]", plan["label_review"])
    current_milestone = current_object.get("milestone")
    current_milestone_title = (
        current_milestone.get("title") if isinstance(current_milestone, dict) else None
    )
    current_labels = current_object.get("labels")
    if (
        current_object.get("title") != content["title"]
        or (current_object.get("description") or "") != content["description"]
        or current_milestone_title != content["milestone_title"]
        or not isinstance(current_labels, list)
        or set(current_labels) != set(label_review["proposed"])
    ):
        raise WorkflowError(
            "merged release MR does not match the approved title, description, labels, and milestone"
        )
    current_project = cast("dict[str, Any]", current["project"])
    release_target_state = collect_release_target_state(
        cast("str", current_project["hostname"]),
        cast("int", current_project["id"]),
        f"v{content['version']}",
        post_merge_sha,
    )
    requests = release_request_specs(
        root,
        current,
        content,
        current_inventory,
        label_review,
        "post_merge",
        post_merge_sha,
        True,
    )
    write_release_request_assets(root, requests)
    binding = release_binding(
        evidence_digest,
        inventory_digest,
        content,
        requests,
        "post_merge",
        post_merge_sha,
        release_target_state,
    )
    markdown = release_publication_markdown(
        root,
        current,
        current_inventory,
        content,
        requests,
        "post_merge",
        post_merge_sha,
        binding,
        True,
    )
    payload = {
        **plan,
        "target": current["target"],
        "evidence_digest": evidence_digest,
        "inventory_digest": inventory_digest,
        "markdown": markdown,
        "stage": "post_merge",
        "release_content": content,
        "requests": requests,
        "post_merge_sha": post_merge_sha,
        "release_target_state": release_target_state,
    }
    path, plan_digest = write_artifact(root, "publication_plan", payload)
    write_companion(path.with_suffix(".md"), markdown)
    for companion in cast("list[dict[str, str]]", payload["companions"]):
        write_companion(path.with_name(f"{plan_digest}-{companion['name']}"), companion["content"])
    stable_plan, stable_markdown = publish_stable_release(
        root, path, plan_digest, binding, markdown
    )
    return {
        "status": "ok",
        "stage": "post_merge",
        "artifact_path": str(path),
        "evidence_path": str(evidence_path),
        "inventory_path": str(inventory_path),
        "plan_path": str(stable_plan),
        "markdown_path": str(stable_markdown),
        "binding": binding,
        "post_merge_sha": post_merge_sha,
        "external_mutations": False,
    }


def git_read(root: Path, *args: str, text: bool = True) -> str | bytes:
    git = shutil.which("git")
    if git is None:
        raise WorkflowError("git is unavailable")
    completed = subprocess.run(
        [git, "-C", str(root), *args], check=False, capture_output=True, text=text
    )
    if completed.returncode:
        raise WorkflowError("local Git input can no longer be read")
    return cast("str | bytes", completed.stdout)


def answers_are_valid(answers: object) -> bool:
    return isinstance(answers, list) and all(
        isinstance(item, dict)
        and nonempty_string(item.get("question_id"))
        and item.get("verdict") in {"confirmed", "refuted", "not_verified"}
        and (nonempty_string(item.get("evidence")) or nonempty_string(item.get("reason")))
        for item in answers
    )


def validate_critic(
    receipt: dict[str, Any], evidence_digest: str, scope_digest: str | None = None
) -> None:
    required = {
        "schema",
        "evidence_digest",
        "run_id",
        "session_id",
        "findings",
        "external_mutations",
    }
    allowed = required | {"scope_digest", "target_finding_ids", "contributors", "question_answers"}
    keys = set(receipt)
    target_finding_ids = receipt.get("target_finding_ids")
    answers = receipt.get("question_answers")
    problems: list[str] = []
    if receipt.get("schema") != "portable-gitlab/critic-receipt/v2":
        problems.append(
            f'$.schema: expected exactly "portable-gitlab/critic-receipt/v2", '
            f"got {json.dumps(receipt.get('schema'))}"
        )
    for key in required:
        if key not in keys:
            problems.append(f"$.{key}: required field is missing")
    for key in keys:
        if key not in allowed:
            problems.append(
                f"$.{key}: unknown field; allowed fields are {', '.join(sorted(allowed))}"
            )
    if "evidence_digest" in keys and receipt["evidence_digest"] != evidence_digest:
        problems.append(
            f"$.evidence_digest: must bind the selected evidence digest {evidence_digest}"
        )
    if scope_digest is not None:
        if receipt.get("scope_digest") != scope_digest:
            problems.append(
                f"$.scope_digest: an incremental receipt must bind the incremental delta "
                f"digest {scope_digest}"
            )
        if not isinstance(target_finding_ids, list):
            problems.append(
                "$.target_finding_ids: an incremental receipt requires the assessed "
                "previous finding IDs"
            )
    if (
        scope_digest is None
        and "scope_digest" in receipt
        and not is_digest(receipt["scope_digest"])
    ):
        problems.append("$.scope_digest: expected a SHA-256 digest")
    if "findings" in keys and not findings_are_valid(receipt["findings"]):
        problems.append(
            "$.findings: every finding requires id, severity, summary, risk, evidence, "
            "consequence, relation_to_change, and minimum_fix"
        )
    if "target_finding_ids" in receipt and (
        not isinstance(target_finding_ids, list)
        or not all(nonempty_string(item) for item in target_finding_ids)
        or len(target_finding_ids) != len(set(target_finding_ids))
    ):
        problems.append("$.target_finding_ids: expected an array of distinct non-empty finding IDs")
    if "question_answers" in receipt and not answers_are_valid(answers):
        problems.append(
            "$.question_answers: every answer requires question_id, verdict "
            "confirmed/refuted/not_verified, real run/session identity, evidence or reason "
            "for the verdict, and the question's context_digest"
        )
    if receipt.get("external_mutations") is not False:
        problems.append("$.external_mutations: must be false")
    if problems:
        raise WorkflowError(
            "critic receipt is invalid:\n" + "\n".join(f" - {item}" for item in problems)
        )
    if not all(
        isinstance(receipt.get(key), str) and receipt[key] for key in ("run_id", "session_id")
    ):
        raise WorkflowError(
            "critic receipt lacks independent run identity: $.run_id and $.session_id "
            "must be non-empty real native identities"
        )
    if "contributors" in receipt:
        contributors = receipt["contributors"]
        if (
            not isinstance(contributors, list)
            or len(contributors) < 2
            or any(not isinstance(item, dict) or "contributors" in item for item in contributors)
        ):
            raise WorkflowError("critic contributors must be distinct individual receipts")
        for item in cast("list[dict[str, Any]]", contributors):
            validate_critic(item, evidence_digest, scope_digest)
        if (
            len({item.get("run_id") for item in contributors}) != len(contributors)
            or len({item.get("session_id") for item in contributors}) != len(contributors)
            or receipt["run_id"] != contributors[0]["run_id"]
            or receipt["session_id"] != contributors[0]["session_id"]
            or any(item.get("scope_digest") != receipt.get("scope_digest") for item in contributors)
            or set(receipt.get("target_finding_ids") or [])
            != {target for item in contributors for target in item.get("target_finding_ids") or []}
            or not equal_json(
                receipt["findings"],
                [finding for item in contributors for finding in item["findings"]],
            )
        ):
            raise WorkflowError("critic aggregate does not preserve independent contributors")


def validate_decision(
    report: dict[str, Any],
    evidence_digest: str,
    receipt: dict[str, Any] | None,
    mode: str,
    context_digest: str | None = None,
    critic_receipt_digest: str | None = None,
) -> None:
    if receipt is not None and any(
        critic.get("run_id") == report.get("run_id")
        or critic.get("session_id") == report.get("session_id")
        for critic in [receipt, *cast("list[dict[str, Any]]", receipt.get("contributors", []))]
    ):
        raise WorkflowError("critic receipt is not independent of the primary review")
    if (
        report.get("schema") != "portable-gitlab/review-decision/v2"
        or report.get("evidence_digest") != evidence_digest
        or (context_digest is not None and report.get("context_digest") != context_digest)
        or (report.get("critic_receipt_digest") if "critic_receipt_digest" in report else None)
        != critic_receipt_digest
        or not is_digest(report.get("finalize_digest"))
        or report.get("mode") != mode
        or report.get("external_mutations") is not False
        or report.get("verdict") not in {"ready", "not_ready", "blocked"}
        or not isinstance(report.get("responses"), list)
        or not isinstance(report.get("unresolved_threads"), list)
    ):
        raise WorkflowError("review decision is schema-invalid")
    response_values = cast("list[dict[str, Any]]", report["responses"])
    response_ids = {
        item["id"]
        for item in response_values
        if isinstance(item, dict)
        and item.get("decision") in {"accept", "reject"}
        and isinstance(item.get("reason"), str)
        and item["reason"]
    }
    finding_subjects = [
        item
        for item in [
            *(
                cast("list[object]", report["findings"])
                if isinstance(report.get("findings"), list)
                else []
            ),
            *(
                cast("list[object]", receipt["findings"])
                if receipt is not None and isinstance(receipt.get("findings"), list)
                else []
            ),
        ]
        if isinstance(item, dict)
    ]
    finding_ids = {item.get("id") for item in finding_subjects}
    required = set(finding_ids)
    if receipt is not None and isinstance(receipt.get("findings"), list):
        for item in cast("list[object]", receipt["findings"]):
            if isinstance(item, dict):
                required.add(item.get("id"))
    for item in cast("list[object]", report["unresolved_threads"]):
        if isinstance(item, dict):
            required.add(item.get("id"))
    if context_digest is not None:
        thread_ids = {
            item.get("id")
            for item in cast("list[object]", report["unresolved_threads"])
            if isinstance(item, dict)
        }
        if (
            len(finding_ids) != len(finding_subjects)
            or any(
                not isinstance(item_id, str)
                or full_match("[A-Za-z0-9][A-Za-z0-9._-]{0,63}", item_id) is None
                for item_id in finding_ids
            )
            or any(
                not isinstance(item_id, str)
                or full_match("thread:[A-Za-z0-9][A-Za-z0-9._-]{0,127}", item_id) is None
                for item_id in thread_ids
            )
            or finding_ids & thread_ids
        ):
            raise WorkflowError("code-review finding and thread subjects are not namespace-safe")
    if None in required or len(response_ids) != len(response_values) or response_ids != required:
        raise WorkflowError(
            "review decision does not account for every finding and unresolved thread"
        )
    response_by_id = {item["id"]: item for item in response_values}
    accepted_findings = [
        item for item in finding_subjects if response_by_id[item["id"]]["decision"] == "accept"
    ]
    for finding in finding_subjects:
        response = response_by_id[finding["id"]]
        override = response.get("severity_override")
        if "severity_override" in response and (
            not isinstance(override, dict)
            or override.get("original_severity") != finding.get("severity")
            or override.get("severity") not in {"critical", "high", "medium", "low"}
            or not nonempty_string(override.get("reason"))
            or response.get("decision") != "accept"
        ):
            raise WorkflowError(
                "severity_override must preserve the original severity and explain the "
                "accepted finding's reassessment"
            )
        if "duplicate_of" in response and (
            response.get("decision") != "reject"
            or response_by_id.get(response["duplicate_of"], {}).get("decision") != "accept"
            or response["duplicate_of"] == finding["id"]
        ):
            raise WorkflowError("duplicate_of must refer to an accepted canonical finding")
    if duplicate_detailed_finding_ids(accepted_findings):
        raise WorkflowError("review decision accepts structurally duplicate findings")
    if mode in {"normal", "deep", "incremental"} and receipt is None:
        raise WorkflowError(
            "normal, deep, and incremental review require an independent critic receipt"
        )
    if mode == "fast" and report.get("low_risk") is not True and receipt is None:
        raise WorkflowError("fast review without critic requires confirmed low-risk scope")
    if report.get("verdict") == "ready" and report.get("blocking_findings") is True:
        raise WorkflowError("blocking findings prohibit ready")


def validate_release_readiness(
    report: dict[str, Any], bundle: dict[str, Any], evidence_digest: str
) -> None:
    required = {"semver", "compatibility", "migration", "rollback", "ci"}
    gates = report.get("gates")
    if (
        report.get("schema") != "portable-gitlab/release-readiness/v2"
        or set(report)
        != {
            "schema",
            "evidence_digest",
            "verdict",
            "readiness",
            "gates",
            "external_mutations",
        }
        or report.get("evidence_digest") != evidence_digest
        or report.get("verdict") not in {"ready", "not_ready", "blocked"}
        or not isinstance(report.get("readiness"), bool)
        or report.get("external_mutations") is not False
        or not isinstance(gates, dict)
        or set(gates) != required
    ):
        raise WorkflowError("release readiness report is schema-invalid")
    identity = {
        "base_sha": bundle.get("base_sha"),
        "start_sha": bundle.get("start_sha"),
        "head_sha": bundle.get("head_sha"),
    }
    for gate in gates.values():
        if (
            not isinstance(gate, dict)
            or gate.get("status") not in {"passed", "failed", "blocked", "not_applicable"}
            or not isinstance(gate.get("evidence"), list)
            or not gate["evidence"]
            or gate.get("range") != identity
        ):
            raise WorkflowError("release readiness gate does not bind exact range and evidence")
    if (report["verdict"] == "ready") != report["readiness"] or not bundle.get(
        "retrieval_complete"
    ):
        raise WorkflowError("incomplete evidence or readiness disagreement prohibits release ready")
    if report["readiness"] and any(gate["status"] != "passed" for gate in gates.values()):
        raise WorkflowError("an unclosed release gate prohibits ready")


def finalize_payload(
    result: dict[str, object], source: Path, evidence: dict[str, Any], kind: str
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        **result,
        "external_mutations": False,
        "evidence_digest": hashlib.sha256(source.read_bytes()).hexdigest(),
        "evidence_kind": kind,
        "evidence_fingerprint_digest": digest(
            fingerprint(evidence) if kind == "evidence_snapshot" else evidence
        ),
    }
    return payload


def validate_finalize_report(
    path: Path, evidence_path: Path, evidence: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    document, report = artifact_payload(path, "finalize_report")
    report_digest = hashlib.sha256(regular_file(path, "finalize report").read_bytes()).hexdigest()
    evidence_digest = hashlib.sha256(
        regular_file(evidence_path, "evidence snapshot").read_bytes()
    ).hexdigest()
    if (
        report.get("status") != "ok"
        or report.get("complete") is not True
        or report.get("evidence_kind") != "evidence_snapshot"
        or report.get("evidence_digest") != evidence_digest
        or report.get("evidence_fingerprint_digest") != digest(fingerprint(evidence))
        or document.get("kind") != "finalize_report"
    ):
        raise WorkflowError("finalize report is stale, incomplete, or does not bind exact evidence")
    return report, report_digest


def run(profile: str, expected: set[str], argv: list[str] | None = None) -> int:
    parser = ContractArgumentParser(
        description="Canonical portable GET-only GitLab workflow helper"
    )
    parser.add_argument("--capabilities", action="store_true")
    subparsers = parser.add_subparsers(dest="command", parser_class=ContractArgumentParser)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--url", action="append")
    prepare.add_argument("--project-url")
    if profile == "mr-prepare":
        prepare.add_argument("--locale", choices=("en", "ru"), default="en")
    scaffold_parser = subparsers.add_parser("scaffold")
    scaffold_parser.add_argument("--bundle", required=True)
    scaffold_parser.add_argument("--content", required=True)
    if profile == "release-prepare":
        scaffold_parser.add_argument("--inventory", required=True)
        inventory = subparsers.add_parser("inventory")
        inventory.add_argument("--evidence", required=True)
        inventory.add_argument("--repo-root", required=True)
        inventory.add_argument("--previous-ref")
        inventory.add_argument("--workers", type=int, default=8)
        post_merge = subparsers.add_parser("post-merge")
        post_merge.add_argument("--plan", required=True)
        post_merge.add_argument("--expected-binding", required=True)
        post_merge.add_argument("--content")
    if profile not in {"mr-prepare", "release-prepare"}:
        batch = subparsers.add_parser("scaffold-batch")
        batch.add_argument("--bundle", required=True)
        batch.add_argument("--content", required=True)
    final = subparsers.add_parser("finalize")
    if profile in {"mr-prepare", "release-prepare"}:
        final.add_argument("--plan", required=True)
        final.add_argument("--expected-binding", required=profile == "release-prepare")
    else:
        final.add_argument("--artifact-root", required=True)
    final.add_argument("--report")
    record = subparsers.add_parser("record-artifact")
    record.add_argument("--kind", choices=("release_readiness",), required=True)
    record.add_argument("--evidence", required=True)
    record.add_argument("--input", required=True)
    try:
        args = parser.parse_args(argv)
    except WorkflowError as exc:
        return error("invalid_input", str(exc))
    if args.capabilities:
        return capabilities(profile)
    mr_locale = getattr(args, "locale", "en")
    try:
        if profile in {"mr-prepare", "release-prepare"} and args.command in {
            "scaffold",
            "finalize",
            "post-merge",
        }:
            if args.command == "scaffold":
                _, input_payload = artifact_payload(Path(args.bundle), "evidence_snapshot")
            else:
                input_path = Path(args.plan)
                if input_path.name == "mr-publication.json":
                    if profile != "mr-prepare":
                        raise WorkflowError("MR publication pointers require mr-prepare")
                    from .mr_publication import resolve_plan

                    input_path = resolve_plan(input_path)
                elif input_path.name == "release-publication.json":
                    if profile != "release-prepare":
                        raise WorkflowError("release publication pointers require release-prepare")
                    input_path = resolve_release_plan(input_path)
                _, input_payload = artifact_payload(input_path, "publication_plan")
            if input_payload.get("profile") != profile:
                raise WorkflowError("artifact profile does not match the invoked skill")
        if profile == "mr-prepare":
            if args.command == "scaffold":
                mr_locale = input_payload.get("project", {}).get("locale", "en")
            elif args.command == "finalize":
                mr_locale = input_payload.get("mr_content", {}).get("locale", "en")
        if args.command == "inventory":
            inventory_module = importlib.import_module("release_inventory")
            inventory_result = inventory_module.prepare_inventory(
                args.evidence,
                args.repo_root,
                args.previous_ref,
                args.workers,
            )
            emit(inventory_result)
            return 0 if inventory_result["status"] == "ok" else 2
        if args.command == "post-merge":
            result = post_merge_plan(args.plan, args.expected_binding, args.content)
            emit(result)
            return 0
        if args.command == "prepare":
            if bool(args.url) == bool(args.project_url):
                raise WorkflowError("provide exact --url target or --project-url, but not both")
            if args.project_url and profile != "task-prepare":
                raise WorkflowError("project creation mode is only available for task preparation")
            if profile in {"mr-prepare", "release-prepare"} and len(args.url or []) != 1:
                raise WorkflowError(f"{profile} accepts exactly one --url target")
            targets = (
                [parse_target(value, expected) for value in args.url]
                if args.url
                else [parse_project(args.project_url)]
            )
            results = []
            for target in targets:
                try:
                    bundle = collect(target, profile, locale=getattr(args, "locale", "en"))
                    item = {
                        "target": target["url"],
                        "status": "ok",
                        "artifact_path": bundle.get("preview_artifact_path"),
                        "digest": bundle.get("preview_digest"),
                        "artifact_root": bundle["artifact_root"],
                        "head_sha": bundle["head_sha"],
                        "base_sha": bundle.get("base_sha"),
                        "start_sha": bundle.get("start_sha"),
                        "complete": bundle["retrieval_complete"],
                        "components_complete": bundle["components_complete"],
                    }
                    if profile == "mr-prepare":
                        from .mr_publication import text as mr_text

                        item["presentation"] = {
                            "fallback_sections": {
                                key: mr_text(mr_locale)[key]
                                for key in (
                                    "context",
                                    "changes",
                                    "compatibility",
                                    "verification",
                                    "references",
                                )
                            }
                        }
                        if not bundle["retrieval_complete"]:
                            item["status"] = "incomplete"
                    results.append(item)
                except WorkflowError as exc:
                    print(redact(str(exc)), file=sys.stderr)
                    results.append(
                        {"target": target["url"], "status": "error", "error": redact(str(exc))}
                    )
            status = "ok" if all(item["status"] == "ok" for item in results) else "partial"
            mr_chat: dict[str, str] = {}
            if profile == "mr-prepare" and status != "ok":
                from .mr_publication import blocked_chat

                reason = str(results[0].get("error", "evidence collection is incomplete"))
                mr_chat["chat"] = blocked_chat(mr_locale, reason)
            emit(
                {
                    **mr_chat,
                    "status": status,
                    "summary": {
                        "tldr": "Completed GET-only GitLab evidence preparation.",
                        "scope": [item["target"] for item in results],
                        "risks": ["one or more targets failed"] if status != "ok" else [],
                        "checks": [
                            "exact target identity",
                            "endpoint allowlist",
                            "pagination completeness",
                            "exact SHA",
                        ],
                    },
                    "items": results,
                    "external_mutations": False,
                }
            )
            return 0 if status == "ok" else 1
        if args.command in {"scaffold", "scaffold-batch"}:
            plan_name = (
                "release-publication.md"
                if profile == "release-prepare"
                else "publication-plan.md"
                if args.command == "scaffold"
                else "batch-publication-plan.md"
            )
            scaffold_result = scaffold(
                args.bundle,
                args.content,
                plan_name,
                getattr(args, "inventory", None),
            )
            emit(scaffold_result)
            return 2 if profile == "mr-prepare" and scaffold_result["status"] != "ok" else 0
        if args.command == "finalize":
            if profile in {"mr-prepare", "release-prepare"}:
                result, root, evidence_path, bundle = finalize_plan(
                    args.plan, getattr(args, "expected_binding", None)
                )
            else:
                pointer_name = "current.json"
                result = finalize(args.artifact_root, pointer_name)
                root = artifact_root(Path(args.artifact_root))
                evidence_path, bundle = evidence_from_root(root, pointer_name)
            result = finalize_payload(result, evidence_path, bundle, "evidence_snapshot")
            if profile == "release-review":
                if not args.report:
                    raise WorkflowError("release review finalize requires --report")
                readiness_document, readiness = artifact_payload(
                    Path(args.report), "release_readiness"
                )
                validate_release_readiness(
                    readiness,
                    bundle,
                    hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
                )
                result["release_readiness_valid"] = True
                result["release_readiness_digest"] = hashlib.sha256(
                    canonical(readiness_document)
                ).hexdigest()
            path, artifact_digest = write_artifact(root, "finalize_report", result)
            response: dict[str, Any] = {
                "status": result["status"],
                "summary": {
                    "tldr": "Rechecked evidence freshness.",
                    "scope": [],
                    "risks": result.get("changed", []),
                    "checks": [
                        "exact identity",
                        "SHA",
                        "labels",
                        "discussions",
                        "diff",
                        "pipelines",
                        "completeness",
                    ],
                },
                "artifact_path": str(path),
                "digest": artifact_digest,
                "result": result,
                "external_mutations": False,
            }
            if profile == "mr-prepare":
                from .mr_publication import freshness_chat

                response["chat"] = freshness_chat(mr_locale, result)
            emit(response)
            return 0 if result["status"] in {"ok", "not_applicable"} else 2
        if args.command == "record-artifact":
            evidence_doc, evidence = artifact_payload(Path(args.evidence), "evidence_snapshot")
            evidence_digest = hashlib.sha256(canonical(evidence_doc)).hexdigest()
            value = read_json(Path(args.input), "artifact input")
            validate_release_readiness(value, evidence, evidence_digest)
            root = artifact_root(Path(str(evidence["artifact_root"])))
            path, artifact_digest = write_artifact(root, args.kind, value)
            response = {
                "status": "ok",
                "summary": {
                    "tldr": "Saved a private schema-valid artifact.",
                    "scope": [],
                    "risks": [],
                    "checks": ["schema", "evidence digest", "content address"],
                },
                "artifact_path": str(path),
                "digest": artifact_digest,
                "external_mutations": False,
            }
            emit(response)
            return 0
        return error("invalid_command", "a supported subcommand is required")
    except WorkflowError as exc:
        code = "tool_unavailable" if "unavailable" in str(exc) else "invalid_input"
        if profile == "mr-prepare":
            from .mr_publication import blocked_chat

            emit(
                {
                    "status": "error",
                    "error": {"code": code, "message": str(exc)},
                    "chat": blocked_chat(mr_locale, str(exc)),
                    "external_mutations": False,
                }
            )
            return 3 if code == "tool_unavailable" else 2
        return error(code, str(exc), 3 if code == "tool_unavailable" else 2)
