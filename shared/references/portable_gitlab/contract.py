#!/usr/bin/env python3
"""Canonical, GET-only GitLab evidence and local publication-plan contract."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, cast
from urllib.parse import quote as urlquote
from urllib.parse import urlsplit

MAX_BYTES = 8 * 1024 * 1024
MAX_PAGES = 1_000
ARTIFACT_VERSION = 2
ARTIFACT_SCHEMA_NAME = "artifact-contracts-v2.schema.json"
URL_RE = re.compile(
    r"^https://(?P<host>[^/?#]+)/(?P<project>.+?)/-/(?P<kind>issues|merge_requests)/(?P<iid>[1-9][0-9]*)/?$"
)
SECRET_RE = re.compile(r"(?i)(token|password|secret|private[_-]?token)\s*[=:]\s*[^\s,]+")
SEMVER_RE = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
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
    "critic_receipt",
    "review_decision",
    "release_readiness",
    "finalize_report",
    "local_wip_snapshot",
}


class WorkflowError(ValueError):
    """Expected contract or collection failure."""


class ContractArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise WorkflowError(message)


def redact(value: str) -> str:
    return SECRET_RE.sub(r"\1=[REDACTED]", value)


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
    path.mkdir(parents=True, exist_ok=True)
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise WorkflowError("artifact directory must be a real directory")
    path.chmod(0o700)
    return path.resolve()


def state_directory(profile: str, target: dict[str, object]) -> Path:
    """Collection ownership is target identity, never the calling profile."""
    if profile not in PROFILES:
        raise WorkflowError("workflow profile is unsafe")
    home = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    identity = f"{target.get('hostname', 'local')}:{target.get('project_id', target.get('project_path', 'local'))}:{target.get('kind', 'local')}:{target.get('iid', 'local')}"
    return private_directory(
        home / "agent-skills" / "gitlab" / hashlib.sha256(identity.encode()).hexdigest()[:32]
    )


def artifact_root(path: Path) -> Path:
    home = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
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
    target = path.resolve()
    if target.parent != path.parent.resolve():
        raise WorkflowError("state path escapes its directory")
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_bytes(canonical(value))
    temporary.chmod(0o600)
    os.replace(temporary, target)


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
    return all(
        isinstance(item, dict)
        and (set(item) == legacy or set(item) == detailed)
        and nonempty_string(item.get("id"))
        and (
            set(item) == legacy
            or (
                item.get("severity") in {"critical", "high", "medium", "low"}
                and all(
                    nonempty_string(item.get(key))
                    for key in detailed - {"id", "severity", "evidence"}
                )
                and isinstance(item.get("evidence"), list)
                and bool(item["evidence"])
                and all(nonempty_string(value) for value in item["evidence"])
            )
        )
        for item in value
    )


def detailed_findings_are_valid(value: object) -> bool:
    return findings_are_valid(value) and all(
        isinstance(item, dict) and set(item) != {"id"} for item in cast(list[object], value)
    )


def thread_decisions_are_valid(value: object) -> bool:
    required = {"id", "url", "state", "assessment", "rationale", "outcome", "proposed_response"}
    return isinstance(value, list) and all(
        isinstance(item, dict)
        and set(item) == required
        and all(nonempty_string(item.get(key)) for key in ("id", "url", "rationale"))
        and item.get("state") in {"open", "resolved", "plain"}
        and item.get("assessment")
        in {
            "accepted",
            "fixed",
            "false_positive",
            "duplicate",
            "not_related",
            "question",
            "neutral",
        }
        and item.get("outcome") in {"no_publication", "local_fix"}
        and (
            item.get("proposed_response") is None or isinstance(item.get("proposed_response"), str)
        )
        for item in value
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
    name = cast(str, value["name"])
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
        item is None or isinstance(item, str) and item in LABEL_ROLE_VALUES[role]
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
    current = cast(list[str], raw_current)
    semantics_by_name: dict[str, set[tuple[str, str]]] = {}
    for item in cast(list[object], labels_component.get("items", [])):
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
    decisions = cast(list[object], value["decisions"])
    required = {"role", "intent", "current", "desired_label", "action", "reason"}
    if not all(
        isinstance(item, dict)
        and set(item) == required
        and isinstance(item.get("role"), str)
        and item["role"] in LABEL_ROLE_VALUES
        and (
            item.get("intent") is None
            or isinstance(item.get("intent"), str)
            and item["intent"] in LABEL_ROLE_VALUES[item["role"]]
        )
        and isinstance(item.get("current"), list)
        and all(isinstance(name, str) for name in item["current"])
        and (item.get("desired_label") is None or isinstance(item.get("desired_label"), str))
        and item.get("action") in {"keep", "change", "unsupported", "unresolved"}
        and nonempty_string(item.get("reason"))
        for item in decisions
    ):
        return False
    typed_decisions = cast(list[dict[str, Any]], decisions)
    roles = [item["role"] for item in typed_decisions]
    current = cast(list[str], value["current"])
    add = cast(list[str], value["add"])
    remove = cast(list[str], value["remove"])
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
            or not value["unresolved"]
            and all(item["action"] != "unresolved" for item in typed_decisions)
        )
        and value["proposed"] == expected
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
        if schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(value)
            except ValueError:
                return False
    if isinstance(value, int) and not isinstance(value, bool):
        if isinstance(schema.get("minimum"), int) and value < schema["minimum"]:
            return False
    if isinstance(value, list):
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
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
            or schema_valid(cast(dict[str, Any], properties[key]), item, root)
            for key, item in value.items()
            if key in properties
        ):
            return False
    return True


def validate_v2_artifact(value: dict[str, Any], kind: str) -> None:
    """Enforce the canonical v2 schema without a runtime-only dependency."""
    schema = artifact_schema()
    if not schema_valid(schema, value, schema):
        raise WorkflowError("artifact does not satisfy the canonical schema")
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
    try:
        datetime.fromisoformat(cast(str, envelope["created_at"]))
    except ValueError as exc:
        raise WorkflowError("artifact timestamp is schema-invalid") from exc
    payload = cast(dict[str, Any], envelope["payload"])
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
                for key in ("commits", "merge_requests", "direct_commits", "errors", "warnings")
            )
            or not isinstance(payload["complete"], bool)
            or not nonempty_string(payload["artifact_root"])
            or not nonempty_string(payload["prepared_at"])
            or not isinstance(counts, dict)
            or set(counts) != {"commits", "merge_requests", "direct_commits", "errors", "warnings"}
            or not all(
                isinstance(item, int) and not isinstance(item, bool) and item >= 0
                for item in counts.values()
            )
        ):
            raise WorkflowError("release inventory payload is schema-invalid")
    elif kind == "review_context":
        required = {
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
        exact_keys(payload, required, "review context payload")
        counts = payload["counts"]
        exact_git = payload["exact_git"]
        if (
            payload["schema_version"] != ARTIFACT_VERSION
            or payload["profile"] != "code-review"
            or payload["external_mutations"] is not False
            or not is_digest(payload["evidence_digest"])
            or not isinstance(payload["target"], dict)
            or payload["role"] not in {"author", "reviewer"}
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
            or not all(
                isinstance(item, int) and not isinstance(item, bool) and item >= 0
                for item in counts.values()
            )
            or not isinstance(exact_git, dict)
            or set(exact_git)
            != {"repo_root", "refs", "changed_paths", "diff_sha256", "complete", "errors"}
            or not nonempty_string(exact_git.get("repo_root"))
            or not isinstance(exact_git.get("refs"), dict)
            or not isinstance(exact_git.get("changed_paths"), list)
            or not all(isinstance(item, str) for item in exact_git["changed_paths"])
            or not is_digest(exact_git.get("diff_sha256"))
            and exact_git.get("diff_sha256") is not None
            or not isinstance(exact_git.get("complete"), bool)
            or not isinstance(exact_git.get("errors"), list)
            or not all(isinstance(item, str) for item in exact_git["errors"])
        ):
            raise WorkflowError("review context payload is schema-invalid")
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
        release_fields = {"inventory_digest", "release_version", "companions"}
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
            keys_valid = actual_keys == expected_keys or actual_keys == (
                expected_keys | label_fields
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
                    or not isinstance(payload.get("release_version"), str)
                    or SEMVER_RE.fullmatch(cast(str, payload.get("release_version"))) is None
                    or not companions_are_valid(payload.get("companions"))
                )
            )
            or ("label_review" in payload and not label_review_is_valid(payload["label_review"]))
        ):
            raise WorkflowError("publication plan payload is schema-invalid")
    elif kind == "review_plan":
        required = {
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
            "checks",
            "findings",
            "thread_decisions",
            "markdown",
        }
        exact_keys(payload, required, "review plan payload")
        if (
            payload["profile"] != "code-review"
            or payload["external_mutations"] is not False
            or not all(
                is_digest(payload[key])
                for key in ("evidence_digest", "context_digest", "decision_digest")
            )
            or not isinstance(payload["target"], dict)
            or payload["role"] not in {"author", "reviewer"}
            or payload["mode"] not in {"fast", "normal", "deep"}
            or payload["verdict"] not in {"ready", "not_ready", "blocked"}
            or not isinstance(payload["complete"], bool)
            or not all(
                nonempty_string(payload[key]) for key in ("summary", "architecture_assessment")
            )
            or payload["semver_impact"]
            not in {"major", "minor", "patch", "none", "not_applicable", "unknown"}
            or not isinstance(payload["checks"], list)
            or not all(nonempty_string(item) for item in payload["checks"])
            or not detailed_findings_are_valid(payload["findings"])
            or not thread_decisions_are_valid(payload["thread_decisions"])
            or not isinstance(payload["markdown"], str)
        ):
            raise WorkflowError("review plan payload is schema-invalid")
    elif kind in {"analysis_report", "critic_receipt"}:
        exact_keys(
            payload,
            {
                "schema",
                "evidence_digest",
                "run_id",
                "session_id",
                "findings",
                "external_mutations",
            },
            f"{kind} payload",
        )
        expected = "analysis-report" if kind == "analysis_report" else "critic-receipt"
        if (
            payload["schema"] != f"portable-gitlab/{expected}/v2"
            or not is_digest(payload["evidence_digest"])
            or not all(nonempty_string(payload[key]) for key in ("run_id", "session_id"))
            or not findings_are_valid(payload["findings"])
            or payload["external_mutations"] is not False
        ):
            raise WorkflowError(f"{kind} payload is schema-invalid")
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
        if not required.issubset(payload) or not set(payload).issubset(
            required | {"context_digest", "low_risk", "blocking_findings", "external_mutations"}
        ):
            raise WorkflowError("review decision payload has unknown or missing fields")
        responses = payload["responses"]
        if (
            payload["schema"] != "portable-gitlab/review-decision/v2"
            or not is_digest(payload["evidence_digest"])
            or not is_digest(payload["finalize_digest"])
            or ("context_digest" in payload and not is_digest(payload["context_digest"]))
            or payload["mode"] not in {"fast", "normal", "deep"}
            or payload["verdict"] not in {"ready", "not_ready", "blocked"}
            or not all(nonempty_string(payload[key]) for key in ("run_id", "session_id"))
            or not findings_are_valid(payload["findings"])
            or not findings_are_valid(payload["unresolved_threads"])
            or not isinstance(responses, list)
            or not all(
                isinstance(item, dict)
                and set(item) == {"id", "decision", "reason"}
                and nonempty_string(item.get("id"))
                and item.get("decision") in {"accept", "reject"}
                and nonempty_string(item.get("reason"))
                for item in responses
            )
            or ("low_risk" in payload and not isinstance(payload["low_risk"], bool))
            or (
                "blocking_findings" in payload
                and not isinstance(payload["blocking_findings"], bool)
            )
            or ("external_mutations" in payload and payload["external_mutations"] is not False)
        ):
            raise WorkflowError("review decision payload is schema-invalid")
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
            or payload["evidence_kind"] not in {"evidence_snapshot", "local_wip_snapshot"}
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
    else:
        raise WorkflowError("unknown artifact kind")


def allowed_endpoint(endpoint: str) -> bool:
    # These are the complete collection endpoints. Query values are generated, never caller input.
    return bool(
        re.fullmatch(
            r"(?:user|projects/(?:[^/?]+|[0-9]+/(?:labels|pipelines)(?:\?[^#]+)?|[0-9]+/(?:issues|merge_requests)/[1-9][0-9]*(?:/(?:discussions|changes|commits|notes))?(?:\?[^#]+)?|[0-9]+/repository/tags/[^/?#]+|[0-9]+/repository/commits/[0-9a-fA-F]{1,128}/merge_requests(?:\?[^#]+)?))",
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


def paginated(hostname: str, endpoint: str) -> dict[str, object]:
    items: list[object] = []
    seen: set[str] = set()
    page_digests: set[str] = set()
    errors: list[str] = []
    for page in range(1, MAX_PAGES + 1):
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
        if len(value) < 100:
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
        "pages": MAX_PAGES if not errors else page,
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


def collect(target: dict[str, object], profile: str, *, persist: bool = True) -> dict[str, object]:
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
            "project": {"id": project_id, "path": project_path, "hostname": hostname},
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
            cast(dict[str, Any], object_value["diff_refs"])
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
                    changed = component(cast(list[object], changes_value["changes"]), pages=1)
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
                    cast(list[object], changed["items"]),
                    complete=False,
                    errors=[*cast(list[str], changed["errors"]), "exact diff refs are unavailable"],
                    pages=cast(int, changed["pages"]),
                    truncated=True,
                )
            if isinstance(head_sha, str) and head_sha:
                commits = paginated(hostname, f"projects/{project_id}/merge_requests/{iid}/commits")
                if not any(
                    isinstance(commit, dict) and commit.get("id") == head_sha
                    for commit in cast(list[object], commits["items"])
                ):
                    commits = component(
                        cast(list[object], commits["items"]),
                        complete=False,
                        errors=[
                            *cast(list[str], commits["errors"]),
                            "commits do not bind exact head SHA",
                        ],
                        pages=cast(int, commits["pages"]),
                        truncated=True,
                    )
                pipelines = paginated(
                    hostname, f"projects/{project_id}/pipelines?sha={urlquote(head_sha, safe='')}"
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
            "project": {"id": project_id, "path": project_path, "hostname": hostname},
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
    components_complete = cast(dict[str, bool], bundle["components_complete"])
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


def evidence_from_root(root: Path) -> tuple[Path, dict[str, Any]]:
    try:
        pointer = read_json(root / "current.json", "collection state")
        path = pointer.get("evidence_path")
        if not isinstance(path, str):
            raise WorkflowError("collection state has no evidence snapshot")
        source = Path(path)
        if source.parent.parent.parent != root:
            raise WorkflowError("evidence snapshot escapes collection root")
        _, payload = artifact_payload(source, "evidence_snapshot")
        return source, payload
    except WorkflowError:
        # Legacy v1 state had one immutable bundle.json instead of a current pointer.
        source = root / "bundle.json"
        _, payload = artifact_payload(source, "evidence_snapshot")
        return source, payload


def marked_preview(label: str, value: str) -> str:
    separator = "" if value.endswith("\n") else "\n"
    return f"<!-- {label} START -->\n{value}{separator}<!-- {label} END -->"


def pipeline_summary(bundle: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    pipelines = bundle.get("pipelines")
    head_sha = bundle.get("head_sha")
    if not isinstance(pipelines, dict) or pipelines.get("complete") is not True:
        return "unverified: collection incomplete", None
    if not isinstance(head_sha, str) or not head_sha:
        return "unverified: exact head SHA unavailable", None
    items = pipelines.get("items")
    if not isinstance(items, list):
        return "unverified: pipeline data invalid", None
    exact = [item for item in items if isinstance(item, dict) and item.get("sha") == head_sha]
    if not exact:
        return "missing", None
    pipeline = exact[0]
    for candidate in exact[1:]:
        candidate_id, pipeline_id = candidate.get("id"), pipeline.get("id")
        if isinstance(candidate_id, int) and (
            not isinstance(pipeline_id, int) or candidate_id > pipeline_id
        ):
            pipeline = candidate
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
    if (
        not isinstance(current_title, str)
        or current_description is not None
        and not isinstance(current_description, str)
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
                "Before manual publication, run `finalize --plan` for this JSON envelope; stale or incomplete evidence blocks readiness.",
            ]
        )
        + "\n"
    )


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
    release_inventory: dict[str, Any] | None = None
    inventory_digest: str | None = None
    release_companions: list[dict[str, str]] = []
    label_review: dict[str, Any] | None = None
    content_fields = {"title", "description"}
    if profile in {"mr-prepare", "release-prepare"}:
        content_fields.add("label_intent")
    if profile == "release-prepare":
        if inventory_file is None:
            raise WorkflowError("release publication plan requires --inventory")
        inventory_module = importlib.import_module("release_inventory")
        _, release_inventory, inventory_digest = inventory_module.validate_inventory_binding(
            inventory_file, source
        )
        content_fields |= {"version", "announcement", "illustration_prompt"}
    content_value = exact_keys(read_json(Path(content_file), "content"), content_fields, "content")
    if not nonempty_string(content_value["title"]) or not isinstance(
        content_value["description"], str
    ):
        raise WorkflowError("content requires a non-empty title and a description string")
    content = content_value
    if profile in {"mr-prepare", "release-prepare"}:
        if not label_intent_is_valid(content.get("label_intent")):
            raise WorkflowError("content requires a complete semantic label_intent object")
        label_review = review_labels(bundle, cast(dict[str, str | None], content["label_intent"]))
    if profile == "release-prepare":
        release_label_intent = cast(dict[str, str | None], content["label_intent"])
        if (
            not isinstance(content.get("version"), str)
            or SEMVER_RE.fullmatch(content["version"]) is None
            or not nonempty_string(content.get("description"))
            or not nonempty_string(content.get("announcement"))
            or not nonempty_string(content.get("illustration_prompt"))
            or release_label_intent["change_type"] != "release"
            or release_label_intent["compatibility"] not in {"major", "minor", "patch"}
        ):
            raise WorkflowError(
                "release content requires SemVer, release/compatibility label intent, announcement, and illustration_prompt"
            )
        version = content["version"]
        for name, value in (
            (f"release-description-v{version}.md", content["description"]),
            (f"release-announcement-v{version}.md", content["announcement"]),
            (f"release-illustration-prompt-v{version}.md", content["illustration_prompt"]),
        ):
            release_companions.append(
                {
                    "name": name,
                    "content": value,
                    "sha256": hashlib.sha256(value.encode()).hexdigest(),
                }
            )
    markdown = publication_markdown(bundle, content, release_inventory, label_review)
    complete = (
        bool(bundle.get("retrieval_complete"))
        and (release_inventory is None or release_inventory.get("complete") is True)
        and (label_review is None or label_review.get("complete") is True)
    )
    payload: dict[str, Any] = {
        "profile": bundle.get("profile"),
        "external_mutations": False,
        "target": bundle.get("target"),
        "evidence_digest": evidence_digest,
        "complete": complete,
        "markdown": markdown,
        "plan_name": Path(plan_name).name,
    }
    if profile == "release-prepare":
        payload.update(
            {
                "inventory_digest": inventory_digest,
                "release_version": content["version"],
                "companions": release_companions,
            }
        )
    if label_review is not None:
        payload["label_review"] = label_review
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
    return {
        "status": "ok" if complete else "incomplete",
        "summary": {
            "tldr": "Prepared a local Markdown plan for manual publication.",
            "scope": [str(bundle.get("target", {}).get("url", "local"))],
            "risks": [] if complete else ["collection, inventory, or label intent incomplete"],
            "checks": [
                "schema-valid evidence",
                "content-addressed publication plan",
                *(["exact release inventory"] if release_inventory is not None else []),
                *(["semantic label delta"] if label_review is not None else []),
            ],
        },
        "artifact_path": str(path),
        "digest": plan_digest,
        "markdown_path": str(markdown_path),
        "markdown_digest": markdown_digest,
        "companions": companion_outputs,
        "external_mutations": False,
    }


def fingerprint(bundle: dict[str, Any]) -> dict[str, object]:
    return {
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


def finalize(root_value: str) -> dict[str, object]:
    root = artifact_root(Path(root_value))
    source, baseline = evidence_from_root(root)
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


def plan_context(
    plan_value: str,
) -> tuple[Path, Path, dict[str, Any], str, Path, dict[str, Any], dict[str, Any] | None]:
    plan_path = regular_file(Path(plan_value), "publication plan")
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
        if not label_review_is_valid(label_review):
            raise WorkflowError("publication plan label review is invalid")
        expected_complete = bool(expected_complete) and label_review.get("complete") is True
    if plan.get("profile") == "release-prepare":
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
        expected_complete = bool(expected_complete) and release_inventory.get("complete") is True
        companions = plan.get("companions")
        if not companions_are_valid(companions):
            raise WorkflowError("release publication companions are invalid")
        for companion in cast(list[dict[str, str]], companions):
            companion_path = regular_file(
                plan_path.with_name(f"{plan_digest}-{companion['name']}"),
                "release publication companion",
            )
            if (
                companion_path.read_bytes() != companion["content"].encode()
                or hashlib.sha256(companion_path.read_bytes()).hexdigest() != companion["sha256"]
            ):
                raise WorkflowError("release publication companion does not match the plan")
    if (
        plan.get("profile") != baseline.get("profile")
        or plan.get("target") != baseline.get("target")
        or plan.get("complete") != expected_complete
    ):
        raise WorkflowError("publication plan does not bind its evidence identity")
    return root, plan_path, plan, plan_digest, source, baseline, release_inventory


def finalize_plan(
    plan_value: str,
) -> tuple[dict[str, object], Path, Path, dict[str, Any]]:
    root, _, plan, plan_digest, source, baseline, release_inventory = plan_context(plan_value)
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
    current = collect(target, str(baseline.get("profile", "task-triage")), persist=False)
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


def git_read(root: Path, *args: str, text: bool = True) -> str | bytes:
    git = shutil.which("git")
    if git is None:
        raise WorkflowError("git is unavailable")
    completed = subprocess.run(
        [git, "-C", str(root), *args], check=False, capture_output=True, text=text
    )
    if completed.returncode:
        raise WorkflowError("local Git input can no longer be read")
    return cast(str | bytes, completed.stdout)


def local_section(root: Path, name: str, args: tuple[str, ...]) -> dict[str, object]:
    value = git_read(root, *args)
    assert isinstance(value, str)
    return {
        "name": name,
        "diff": value,
        "sha256": hashlib.sha256(value.encode()).hexdigest(),
        "complete": True,
        "errors": [],
    }


def local_untracked(root: Path) -> dict[str, object]:
    raw = git_read(root, "ls-files", "--others", "--exclude-standard", "-z", text=False)
    assert isinstance(raw, bytes)
    items, errors = [], []
    for encoded in raw.split(b"\0"):
        if not encoded:
            continue
        relative = os.fsdecode(encoded)
        candidate = root / relative
        try:
            meta = candidate.lstat()
        except OSError:
            items.append({"path": relative, "complete": False, "reason": "unreadable"})
            errors.append(relative)
            continue
        if stat.S_ISLNK(meta.st_mode):
            items.append({"path": relative, "complete": False, "reason": "symlink"})
            errors.append(relative)
            continue
        if not stat.S_ISREG(meta.st_mode):
            items.append({"path": relative, "complete": False, "reason": "non_regular"})
            errors.append(relative)
            continue
        if meta.st_size > MAX_BYTES:
            items.append(
                {"path": relative, "size": meta.st_size, "complete": False, "reason": "oversized"}
            )
            errors.append(relative)
            continue
        try:
            data = candidate.read_bytes()
        except OSError:
            items.append({"path": relative, "complete": False, "reason": "unreadable"})
            errors.append(relative)
            continue
        if b"\0" in data:
            items.append(
                {"path": relative, "size": len(data), "complete": False, "reason": "binary"}
            )
            errors.append(relative)
            continue
        items.append(
            {
                "path": relative,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "complete": True,
            }
        )
    return {"items": items, "complete": not errors, "errors": errors}


def local_bundle(repo_root: str, profile: str, ref: str | None) -> dict[str, object]:
    raw_root = Path(repo_root)
    if raw_root.is_symlink():
        raise WorkflowError("repo root must not be a symbolic link")
    root = raw_root.resolve()
    if not (root / ".git").exists():
        raise WorkflowError("repo root must be a real Git checkout")
    head = str(git_read(root, "rev-parse", "HEAD")).strip()
    base = str(git_read(root, "merge-base", ref or "HEAD", "HEAD")).strip() if ref else head
    staged = local_section(root, "staged", ("diff", "--cached", "--binary", "--find-renames", "--"))
    unstaged = local_section(root, "unstaged", ("diff", "--binary", "--find-renames", "--"))
    untracked = local_untracked(root)
    committed = (
        local_section(root, "committed", ("diff", "--binary", "--find-renames", base, head, "--"))
        if ref
        else local_section(
            root, "committed", ("diff", "--binary", "--find-renames", "HEAD", "HEAD", "--")
        )
    )
    identity = {"hostname": "local", "project_path": str(root), "kind": "local", "iid": 1}
    artifact = state_directory(profile, identity)
    bundle: dict[str, object] = {
        "schema_version": ARTIFACT_VERSION,
        "profile": profile,
        "external_mutations": False,
        "repo_root": str(root),
        "base_sha": base,
        "head_sha": head,
        "ref": ref,
        "sections": {
            "committed": committed,
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
        },
        "artifact_root": str(artifact),
    }
    sections = cast(dict[str, dict[str, object]], bundle["sections"])
    bundle["retrieval_complete"] = all(
        bool(section.get("complete")) for section in sections.values()
    )
    return bundle


def finalize_local(bundle_file: str) -> dict[str, object]:
    _, baseline = artifact_payload(Path(bundle_file), "local_wip_snapshot")
    root = baseline.get("repo_root")
    if not isinstance(root, str):
        raise WorkflowError("local evidence identity is incomplete")
    ref = baseline.get("ref")
    if ref is not None and not isinstance(ref, str):
        raise WorkflowError("local evidence ref is invalid")
    current = local_bundle(root, str(baseline.get("profile", "code-review")), ref)
    changed = [
        key
        for key in ("head_sha", "sections", "retrieval_complete")
        if baseline.get(key) != current.get(key)
    ]
    return {
        "status": "ok" if not changed and bool(current.get("retrieval_complete")) else "stale",
        "changed": changed,
        "head_sha": current.get("head_sha"),
        "complete": current.get("retrieval_complete"),
    }


def validate_critic(receipt: dict[str, Any], evidence_digest: str) -> None:
    required = {
        "schema",
        "evidence_digest",
        "run_id",
        "session_id",
        "findings",
        "external_mutations",
    }
    if (
        receipt.get("schema") != "portable-gitlab/critic-receipt/v2"
        or set(receipt) != required
        or receipt.get("evidence_digest") != evidence_digest
        or not findings_are_valid(receipt.get("findings"))
        or receipt.get("external_mutations") is not False
    ):
        raise WorkflowError("critic receipt is schema-invalid or does not bind evidence")
    if not all(
        isinstance(receipt.get(key), str) and receipt[key] for key in ("run_id", "session_id")
    ):
        raise WorkflowError("critic receipt lacks independent run identity")


def validate_decision(
    report: dict[str, Any],
    evidence_digest: str,
    receipt: dict[str, Any] | None,
    mode: str,
    context_digest: str | None = None,
) -> None:
    if (
        report.get("schema") != "portable-gitlab/review-decision/v2"
        or report.get("evidence_digest") != evidence_digest
        or (context_digest is not None and report.get("context_digest") != context_digest)
        or not is_digest(report.get("finalize_digest"))
        or report.get("mode") != mode
        or report.get("external_mutations") is not False
        or report.get("verdict") not in {"ready", "not_ready", "blocked"}
        or not isinstance(report.get("responses"), list)
        or not isinstance(report.get("unresolved_threads"), list)
    ):
        raise WorkflowError("review decision is schema-invalid")
    response_ids = {
        item.get("id")
        for item in report["responses"]
        if isinstance(item, dict)
        and item.get("decision") in {"accept", "reject"}
        and isinstance(item.get("reason"), str)
        and item["reason"]
    }
    required = {item.get("id") for item in report.get("findings", []) if isinstance(item, dict)}
    if receipt is not None:
        required |= {item.get("id") for item in receipt["findings"] if isinstance(item, dict)}
    required |= {item.get("id") for item in report["unresolved_threads"] if isinstance(item, dict)}
    if None in required or not required.issubset(response_ids):
        raise WorkflowError(
            "review decision does not account for every finding and unresolved thread"
        )
    if mode in {"normal", "deep"} and receipt is None:
        raise WorkflowError("normal and deep review require an independent critic receipt")
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
    if profile != "code-review":
        scaffold_parser = subparsers.add_parser("scaffold")
        scaffold_parser.add_argument("--bundle", required=True)
        scaffold_parser.add_argument("--content", required=True)
        if profile == "release-prepare":
            scaffold_parser.add_argument("--inventory", required=True)
    if profile == "release-prepare":
        inventory = subparsers.add_parser("inventory")
        inventory.add_argument("--evidence", required=True)
        inventory.add_argument("--repo-root", required=True)
        inventory.add_argument("--previous-ref")
        inventory.add_argument("--workers", type=int, default=8)
    if profile == "code-review":
        context = subparsers.add_parser("context")
        context.add_argument("--evidence", required=True)
        context.add_argument("--repo-root", required=True)
        review_plan = subparsers.add_parser("scaffold-review")
        review_plan.add_argument("--evidence", required=True)
        review_plan.add_argument("--context", required=True)
        review_plan.add_argument("--decision", required=True)
        review_plan.add_argument("--content", required=True)
    if profile not in {"mr-prepare", "release-prepare", "code-review"}:
        batch = subparsers.add_parser("scaffold-batch")
        batch.add_argument("--bundle", required=True)
        batch.add_argument("--content", required=True)
    final = subparsers.add_parser("finalize")
    if profile in {"mr-prepare", "release-prepare"}:
        final.add_argument("--plan", required=True)
    else:
        final.add_argument("--artifact-root", required=True)
    final.add_argument("--report")
    local = subparsers.add_parser("prepare-local")
    local.add_argument("--repo-root", required=True)
    local.add_argument("--ref")
    local_final = subparsers.add_parser("finalize-local")
    local_final.add_argument("--bundle", required=True)
    mode = subparsers.add_parser("assess-mode")
    mode.add_argument("--mode", choices=("fast", "normal", "deep"), required=True)
    mode.add_argument("--critic-available", action="store_true")
    decision = subparsers.add_parser("finalize-review")
    decision.add_argument("--evidence", required=True)
    decision.add_argument("--report", required=True)
    decision.add_argument("--mode", choices=("fast", "normal", "deep"), required=True)
    decision.add_argument("--critic-receipt")
    decision.add_argument("--finalize-report", required=True)
    if profile == "code-review":
        decision.add_argument("--context", required=True)
    record = subparsers.add_parser("record-artifact")
    record.add_argument(
        "--kind", choices=("analysis_report", "critic_receipt", "release_readiness"), required=True
    )
    record.add_argument("--evidence", required=True)
    record.add_argument("--input", required=True)
    try:
        args = parser.parse_args(argv)
    except WorkflowError as exc:
        return error("invalid_input", str(exc))
    if args.capabilities:
        return capabilities(profile)
    try:
        if args.command == "context":
            context_module = importlib.import_module("review_context")
            context_result = context_module.prepare_context(args.evidence, args.repo_root)
            emit(context_result)
            return 0 if context_result["status"] == "ok" else 2
        if args.command == "scaffold-review":
            context_module = importlib.import_module("review_context")
            emit(
                context_module.scaffold_review(
                    args.evidence,
                    args.context,
                    args.decision,
                    args.content,
                )
            )
            return 0
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
        if args.command == "prepare":
            if bool(args.url) == bool(args.project_url):
                raise WorkflowError("provide exact --url target or --project-url, but not both")
            if args.project_url and profile != "task-prepare":
                raise WorkflowError("project creation mode is only available for task preparation")
            if (
                profile in {"mr-prepare", "release-prepare", "code-review"}
                and len(args.url or []) != 1
            ):
                raise WorkflowError(f"{profile} accepts exactly one --url target")
            targets = (
                [parse_target(value, expected) for value in args.url]
                if args.url
                else [parse_project(args.project_url)]
            )
            results = []
            for target in targets:
                try:
                    bundle = collect(target, profile)
                    results.append(
                        {
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
                    )
                except WorkflowError as exc:
                    print(redact(str(exc)), file=sys.stderr)
                    results.append(
                        {"target": target["url"], "status": "error", "error": redact(str(exc))}
                    )
            status = "ok" if all(item["status"] == "ok" for item in results) else "partial"
            emit(
                {
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
            emit(
                scaffold(
                    args.bundle,
                    args.content,
                    plan_name,
                    getattr(args, "inventory", None),
                )
            )
            return 0
        if args.command == "finalize":
            if profile in {"mr-prepare", "release-prepare"}:
                result, root, evidence_path, bundle = finalize_plan(args.plan)
            else:
                result = finalize(args.artifact_root)
                root = artifact_root(Path(args.artifact_root))
                evidence_path, bundle = evidence_from_root(root)
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
            emit(
                {
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
            )
            return 0 if result["status"] in {"ok", "not_applicable"} else 2
        if args.command == "prepare-local":
            if profile != "code-review":
                raise WorkflowError("local WIP collection is only available for code review")
            bundle = local_bundle(args.repo_root, profile, args.ref)
            root = artifact_root(Path(str(bundle["artifact_root"])))
            path, artifact_digest = write_artifact(root, "local_wip_snapshot", bundle)
            write_json(
                root / "current-local.json",
                {"evidence_path": str(path), "evidence_digest": artifact_digest},
            )
            emit(
                {
                    "status": "ok" if bundle["retrieval_complete"] else "incomplete",
                    "summary": {
                        "tldr": "Collected local WIP evidence: staged, unstaged, and untracked.",
                        "scope": [str(bundle["repo_root"])],
                        "risks": []
                        if bundle["retrieval_complete"]
                        else ["local evidence incomplete"],
                        "checks": [
                            "HEAD",
                            "staged",
                            "unstaged",
                            "non-ignored untracked",
                            "symlink/binary/size",
                        ],
                    },
                    "bundle": str(path),
                    "artifact_path": str(path),
                    "digest": artifact_digest,
                    "head_sha": bundle["head_sha"],
                    "complete": bundle["retrieval_complete"],
                    "external_mutations": False,
                }
            )
            return 0 if bundle["retrieval_complete"] else 2
        if args.command == "finalize-local":
            result = finalize_local(args.bundle)
            _, bundle = artifact_payload(Path(args.bundle), "local_wip_snapshot")
            root = artifact_root(Path(str(bundle["artifact_root"])))
            result = finalize_payload(result, Path(args.bundle), bundle, "local_wip_snapshot")
            path, artifact_digest = write_artifact(root, "finalize_report", result)
            emit(
                {
                    "status": result["status"],
                    "summary": {
                        "tldr": "Checked local WIP evidence freshness.",
                        "scope": [str(bundle["repo_root"])],
                        "risks": result.get("changed", []),
                        "checks": ["HEAD", "all WIP sections"],
                    },
                    "artifact_path": str(path),
                    "digest": artifact_digest,
                    "result": result,
                    "external_mutations": False,
                }
            )
            return 0 if result["status"] == "ok" else 2
        if args.command == "assess-mode":
            if args.mode in {"normal", "deep"} and not args.critic_available:
                emit(
                    {
                        "status": "unsupported",
                        "reason": "independent critic receipt is required",
                        "details": {"mode": args.mode},
                    }
                )
                return 4
            emit(
                {
                    "status": "ok",
                    "mode": args.mode,
                    "independent_critic_required": args.mode in {"normal", "deep"},
                }
            )
            return 0
        if args.command == "record-artifact":
            evidence_doc, evidence = artifact_payload(Path(args.evidence), "evidence_snapshot")
            evidence_digest = hashlib.sha256(canonical(evidence_doc)).hexdigest()
            value = read_json(Path(args.input), "artifact input")
            if args.kind == "critic_receipt":
                validate_critic(value, evidence_digest)
            elif args.kind == "release_readiness":
                validate_release_readiness(value, evidence, evidence_digest)
            elif (
                value.get("schema") != "portable-gitlab/analysis-report/v2"
                or value.get("evidence_digest") != evidence_digest
            ):
                raise WorkflowError("analysis report is schema-invalid or does not bind evidence")
            if (
                evidence.get("profile") == "code-review"
                and args.kind in {"analysis_report", "critic_receipt"}
                and not detailed_findings_are_valid(value.get("findings"))
            ):
                raise WorkflowError("new code review findings require complete structured evidence")
            root = artifact_root(Path(str(evidence["artifact_root"])))
            path, artifact_digest = write_artifact(root, args.kind, value)
            emit(
                {
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
            )
            return 0
        if args.command == "finalize-review":
            evidence_doc, evidence = artifact_payload(Path(args.evidence), "evidence_snapshot")
            evidence_digest = hashlib.sha256(canonical(evidence_doc)).hexdigest()
            root = artifact_root(Path(str(evidence["artifact_root"])))
            # Compare the explicitly supplied immutable snapshot, not current.json.
            review_target = evidence.get("target")
            if not isinstance(review_target, dict):
                raise WorkflowError("review evidence target is missing")
            current = collect(
                review_target, str(evidence.get("profile", "code-review")), persist=False
            )
            if not current.get("retrieval_complete") or fingerprint(evidence) != fingerprint(
                current
            ):
                raise WorkflowError("evidence is stale or incomplete at final review")
            context_digest = None
            if profile == "code-review":
                context_module = importlib.import_module("review_context")
                _, review_context, context_digest = context_module.validate_context_binding(
                    args.context, args.evidence
                )
                current_context = context_module.refresh_context(review_context, args.evidence)
                if (
                    review_context.get("complete") is not True
                    or current_context.get("complete") is not True
                    or context_module.context_fingerprint(review_context)
                    != context_module.context_fingerprint(current_context)
                ):
                    raise WorkflowError("review context is stale or incomplete at final review")
            _, finalize_digest = validate_finalize_report(
                Path(args.finalize_report), Path(args.evidence), evidence
            )
            report = read_json(Path(args.report), "review decision")
            receipt = (
                read_json(Path(args.critic_receipt), "critic receipt")
                if args.critic_receipt
                else None
            )
            if receipt is not None and receipt.get("schema") == "portable-gitlab/critic_receipt/v2":
                _, receipt = artifact_payload(Path(args.critic_receipt), "critic_receipt")
            if receipt is not None:
                validate_critic(receipt, evidence_digest)
                if profile == "code-review" and not detailed_findings_are_valid(
                    receipt.get("findings")
                ):
                    raise WorkflowError("critic findings require complete structured evidence")
                if receipt["run_id"] == report.get("run_id") or receipt["session_id"] == report.get(
                    "session_id"
                ):
                    raise WorkflowError("critic receipt is not independent of the primary review")
            if profile == "code-review" and not detailed_findings_are_valid(report.get("findings")):
                raise WorkflowError("review findings require complete structured evidence")
            validate_decision(report, evidence_digest, receipt, args.mode, context_digest)
            if report["finalize_digest"] != finalize_digest:
                raise WorkflowError("review decision does not bind exact finalize report")
            if not evidence.get("retrieval_complete") or (
                report.get("verdict") == "ready" and report.get("blocking_findings")
            ):
                raise WorkflowError(
                    "incomplete evidence or unresolved blocking findings prohibit ready"
                )
            path, result_digest = write_artifact(root, "review_decision", report)
            emit(
                {
                    "status": "ok",
                    "summary": {
                        "tldr": "Verified the review decision without external mutations.",
                        "scope": [str(evidence.get("target", {}).get("url", "local"))],
                        "risks": [],
                        "checks": [
                            "evidence binding",
                            *(
                                ["role and review context binding"]
                                if profile == "code-review"
                                else []
                            ),
                            "independent critic",
                            "all findings and threads covered",
                        ],
                    },
                    "artifact_path": str(path),
                    "digest": result_digest,
                    "external_mutations": False,
                }
            )
            return 0
        return error("invalid_command", "a supported subcommand is required")
    except WorkflowError as exc:
        code = "tool_unavailable" if "unavailable" in str(exc) else "invalid_input"
        return error(code, str(exc), 3 if code == "tool_unavailable" else 2)
