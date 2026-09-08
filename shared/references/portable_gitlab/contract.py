#!/usr/bin/env python3
"""Canonical, GET-only GitLab evidence and local publication-plan contract."""

from __future__ import annotations

import argparse
import hashlib
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
URL_RE = re.compile(
    r"^https://(?P<host>[^/?#]+)/(?P<project>.+?)/-/(?P<kind>issues|merge_requests)/(?P<iid>[1-9][0-9]*)/?$"
)
SECRET_RE = re.compile(r"(?i)(token|password|secret|private[_-]?token)\s*[=:]\s*[^\s,]+")
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
    "publication_plan",
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
            "external_tools": {"glab": shutil.which("glab") is not None},
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
    return isinstance(value, list) and all(
        isinstance(item, dict) and set(item) == {"id"} and nonempty_string(item.get("id"))
        for item in value
    )


def validate_v2_artifact(value: dict[str, Any], kind: str) -> None:
    """Enforce the canonical v2 schema without a runtime-only dependency."""
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
    elif kind == "publication_plan":
        exact_keys(
            payload,
            {"profile", "target", "evidence_digest", "complete", "markdown", "plan_name"},
            "publication plan payload",
        )
        if not is_digest(payload["evidence_digest"]) or not isinstance(payload["complete"], bool):
            raise WorkflowError("publication plan payload is schema-invalid")
    elif kind in {"analysis_report", "critic_receipt"}:
        exact_keys(
            payload,
            {"schema", "evidence_digest", "run_id", "session_id", "findings"},
            f"{kind} payload",
        )
        expected = "analysis-report" if kind == "analysis_report" else "critic-receipt"
        if (
            payload["schema"] != f"portable-gitlab/{expected}/v2"
            or not is_digest(payload["evidence_digest"])
            or not all(nonempty_string(payload[key]) for key in ("run_id", "session_id"))
            or not findings_are_valid(payload["findings"])
        ):
            raise WorkflowError(f"{kind} payload is schema-invalid")
    elif kind == "review_decision":
        required = {
            "schema",
            "evidence_digest",
            "finalize_digest",
            "verdict",
            "run_id",
            "session_id",
            "findings",
            "unresolved_threads",
            "responses",
        }
        if not required.issubset(payload) or not set(payload).issubset(
            required | {"low_risk", "blocking_findings"}
        ):
            raise WorkflowError("review decision payload has unknown or missing fields")
        responses = payload["responses"]
        if (
            payload["schema"] != "portable-gitlab/review-decision/v2"
            or not is_digest(payload["evidence_digest"])
            or not is_digest(payload["finalize_digest"])
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
        ):
            raise WorkflowError("review decision payload is schema-invalid")
    elif kind == "release_readiness":
        exact_keys(
            payload,
            {"schema", "evidence_digest", "verdict", "readiness", "gates"},
            "release readiness payload",
        )
        gates = payload["gates"]
        if (
            payload["schema"] != "portable-gitlab/release-readiness/v2"
            or not is_digest(payload["evidence_digest"])
            or payload["verdict"] not in {"ready", "not_ready", "blocked"}
            or not isinstance(payload["readiness"], bool)
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
            r"projects/(?:[^/?]+|[0-9]+/(?:labels|pipelines)(?:\?[^#]+)?|[0-9]+/(?:issues|merge_requests)/[1-9][0-9]*(?:/(?:discussions|changes|commits))?(?:\?[^#]+)?)",
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
    labels = paginated(hostname, f"projects/{project_id}/labels")
    if kind == "new_issue":
        bundle: dict[str, object] = {
            "schema_version": ARTIFACT_VERSION,
            "profile": profile,
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


def publication_markdown(bundle: dict[str, Any], content: dict[str, Any]) -> str:
    target = bundle.get("target", {})
    return (
        "\n".join(
            [
                "# Проверенный план публикации",
                "",
                f"- Target: {target.get('url', 'local')}",
                f"- Base SHA: {bundle.get('base_sha') or 'не применимо'}",
                f"- Start SHA: {bundle.get('start_sha') or 'не применимо'}",
                f"- Head SHA: {bundle.get('head_sha') or 'не применимо'}",
                f"- Полнота collection: {'полная' if bundle.get('retrieval_complete') else 'частичная'}",
                "- `external_mutations=false`: план не выполняет и не предлагает автоматические publish/resolve/approve/merge операции.",
                "",
                "## Предлагаемые тексты",
                "",
                f"### Заголовок\n\n{content.get('title', '') or 'Без изменений.'}",
                f"\n### Описание\n\n{content.get('description', '') or 'Без изменений.'}",
                "",
                "Перед ручной публикацией выполни `finalize`; stale или incomplete evidence блокируют ready.",
            ]
        )
        + "\n"
    )


def scaffold(bundle_file: str, content_file: str, plan_name: str) -> dict[str, object]:
    source = Path(bundle_file)
    _, bundle = artifact_payload(source, "evidence_snapshot")
    root = artifact_root(Path(str(bundle["artifact_root"])))
    content = read_json(Path(content_file), "content")
    markdown = publication_markdown(bundle, content)
    payload = {
        "profile": bundle.get("profile"),
        "target": bundle.get("target"),
        "evidence_digest": hashlib.sha256(
            regular_file(source, "evidence snapshot").read_bytes()
        ).hexdigest(),
        "complete": bundle.get("retrieval_complete"),
        "markdown": markdown,
        "plan_name": Path(plan_name).name,
    }
    path, plan_digest = write_artifact(root, "publication_plan", payload)
    return {
        "status": "ok" if bundle.get("retrieval_complete") else "incomplete",
        "summary": {
            "tldr": "Подготовлен локальный Markdown-план ручной публикации.",
            "scope": [str(bundle.get("target", {}).get("url", "local"))],
            "risks": [] if bundle.get("retrieval_complete") else ["collection incomplete"],
            "checks": ["schema-valid evidence", "content-addressed publication plan"],
        },
        "artifact_path": str(path),
        "digest": plan_digest,
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
    required = {"schema", "evidence_digest", "run_id", "session_id", "findings"}
    if (
        receipt.get("schema") != "portable-gitlab/critic-receipt/v2"
        or not required.issubset(receipt)
        or receipt.get("evidence_digest") != evidence_digest
        or not findings_are_valid(receipt.get("findings"))
    ):
        raise WorkflowError("critic receipt is schema-invalid or does not bind evidence")
    if not all(
        isinstance(receipt.get(key), str) and receipt[key] for key in ("run_id", "session_id")
    ):
        raise WorkflowError("critic receipt lacks independent run identity")


def validate_decision(
    report: dict[str, Any], evidence_digest: str, receipt: dict[str, Any] | None, mode: str
) -> None:
    if (
        report.get("schema") != "portable-gitlab/review-decision/v2"
        or report.get("evidence_digest") != evidence_digest
        or not is_digest(report.get("finalize_digest"))
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
        or report.get("evidence_digest") != evidence_digest
        or report.get("verdict") not in {"ready", "not_ready", "blocked"}
        or not isinstance(report.get("readiness"), bool)
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
    scaffold_parser = subparsers.add_parser("scaffold")
    scaffold_parser.add_argument("--bundle", required=True)
    scaffold_parser.add_argument("--content", required=True)
    batch = subparsers.add_parser("scaffold-batch")
    batch.add_argument("--bundle", required=True)
    batch.add_argument("--content", required=True)
    final = subparsers.add_parser("finalize")
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
        if args.command == "prepare":
            if bool(args.url) == bool(args.project_url):
                raise WorkflowError("provide exact --url target or --project-url, but not both")
            if args.project_url and profile != "task-prepare":
                raise WorkflowError("project creation mode is only available for task preparation")
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
                        "tldr": "Завершена GET-only подготовка GitLab evidence.",
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
            emit(
                scaffold(
                    args.bundle,
                    args.content,
                    "publication-plan.md"
                    if args.command == "scaffold"
                    else "batch-publication-plan.md",
                )
            )
            return 0
        if args.command == "finalize":
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
                        "tldr": "Повторно проверена актуальность evidence.",
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
                        "tldr": "Собраны local WIP evidence: staged, unstaged и untracked.",
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
                        "tldr": "Проверена актуальность local WIP evidence.",
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
            root = artifact_root(Path(str(evidence["artifact_root"])))
            path, artifact_digest = write_artifact(root, args.kind, value)
            emit(
                {
                    "status": "ok",
                    "summary": {
                        "tldr": "Сохранён private schema-valid artifact.",
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
                if receipt["run_id"] == report.get("run_id") or receipt["session_id"] == report.get(
                    "session_id"
                ):
                    raise WorkflowError("critic receipt is not independent of the primary review")
            validate_decision(report, evidence_digest, receipt, args.mode)
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
                        "tldr": "Проверено review decision без внешних мутаций.",
                        "scope": [str(evidence.get("target", {}).get("url", "local"))],
                        "risks": [],
                        "checks": [
                            "evidence binding",
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
