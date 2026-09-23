#!/usr/bin/env python3
"""Collect and persist bounded GitLab task-triage evidence and reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import tempfile
import urllib.parse
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, NoReturn, TypeGuard

from .release_planning import PlanningError
from .release_planning import validate as validate_release_plan

ISSUE_RE = re.compile(
    r"https://(?P<host>[A-Za-z0-9.-]+)/(?P<project>.+?)/-/(?:issues|work_items)/(?P<iid>[1-9][0-9]*)/?$"
)
COLLECTION_RE = re.compile(
    r"https://(?P<host>[A-Za-z0-9.-]+)/(?P<project>.+?)/-/(?:issues|work_items)/?$"
)
DIGEST_RE = re.compile(r"[a-f0-9]{64}")
MAX_PAGES = 100
MAX_ITEMS = 500
ACTUALITY = {"current", "implemented", "obsolete", "duplicate", "unknown"}
VERDICTS = {"ready", "needs_clarification", "blocked"}
INFORMATION_ACTIONS = {"none", "new", "ping_1", "ping_2", "close"}
TEXT = {
    "en": {
        "summary": "Task triage summary",
        "status": "Status",
        "complete": "complete",
        "partial": "partial",
        "collection": "Collection evidence",
        "analysis": "Analysis",
        "first": "First tasks",
        "parallel": "Parallel groups",
        "questions": "Questions",
        "reports": "Detailed reports",
        "source": "Source",
        "actuality": "Actuality",
        "quality": "Quality",
        "decision": "Planning decision",
        "planning": "Planning verdict",
        "release": "Target release",
        "milestone": "Milestone",
        "severity": "Severity",
        "priority": "Priority",
        "quality_findings": "Quality findings",
        "relations": "Duplicates and relations",
        "merge_requests": "Merge requests",
        "release_planning": "Release planning",
        "recommendations": "Recommendations",
        "commands": "Manual commands",
        "none": "None observed.",
        "no_changes": "No GitLab changes are recommended.",
        "preview": "Preview",
        "command": "Command",
        "action_title": "Update title",
        "action_description": "Update description",
        "action_labels": "Update labels",
        "action_milestone": "Update milestone",
        "action_create_milestone": "Create milestone",
        "action_link": "Create issue link",
        "action_message": "Publish message",
        "action_information_new": "Publish information request",
        "action_information_ping_1": "Publish first follow-up",
        "action_information_ping_2": "Publish second follow-up",
        "action_information_close": "Publish stale closure message",
        "action_close": "Close issue",
    },
    "ru": {
        "summary": "Сводка триажа задач",
        "status": "Статус",
        "complete": "завершён",
        "partial": "частичный",
        "collection": "Снимок коллекции",
        "analysis": "Анализ",
        "first": "Первые задачи",
        "parallel": "Параллельные группы",
        "questions": "Вопросы",
        "reports": "Подробные отчёты",
        "source": "Источник",
        "actuality": "Актуальность",
        "quality": "Качество",
        "decision": "Решение по планированию",
        "planning": "Готовность планирования",
        "release": "Целевой релиз",
        "milestone": "Майлстоун",
        "severity": "Критичность",
        "priority": "Приоритет",
        "quality_findings": "Замечания к качеству",
        "relations": "Дубликаты и связи",
        "merge_requests": "Связанные MR",
        "release_planning": "Планирование релиза",
        "recommendations": "Рекомендации",
        "commands": "Ручные команды",
        "none": "Ничего не обнаружено.",
        "no_changes": "Изменения в GitLab не рекомендуются.",
        "preview": "Предпросмотр",
        "command": "Команда",
        "action_title": "Обновить заголовок",
        "action_description": "Обновить описание",
        "action_labels": "Обновить лейблы",
        "action_milestone": "Обновить майлстоун",
        "action_create_milestone": "Создать майлстоун",
        "action_link": "Создать связь задач",
        "action_message": "Опубликовать сообщение",
        "action_information_new": "Опубликовать запрос информации",
        "action_information_ping_1": "Опубликовать первый пинг",
        "action_information_ping_2": "Опубликовать второй пинг",
        "action_information_close": "Опубликовать финальное сообщение",
        "action_close": "Закрыть задачу",
    },
}
RU_VALUES: dict[str, dict[str | None, str]] = {
    "actuality": {
        "current": "актуальна",
        "implemented": "реализована",
        "obsolete": "устарела",
        "duplicate": "дубликат",
        "unknown": "неизвестна",
    },
    "quality": {
        "ready": "готово",
        "needs_clarification": "нужны уточнения",
        "blocked": "заблокировано",
    },
    "decision": {
        "accepted": "принято",
        "deferred": "отложено",
        "rejected": "отклонено",
        "duplicate": "дубликат",
        "obsolete": "устарело",
    },
    "planning": {
        "ready": "готова",
        "needs_clarification": "нужны уточнения",
        "blocked": "заблокирована",
    },
    "milestone": {
        "selected": "выбран",
        "create": "требуется создать",
        "remove": "требуется снять",
        "none": "не назначен",
    },
    "release": {None: "не определён"},
}


class WorkflowError(ValueError):
    """Expected safe workflow failure."""


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise WorkflowError(message)


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise WorkflowError("state directory must be a real directory")
    path.chmod(0o700)
    return path.resolve()


def atomic_write(path: Path, content: bytes) -> None:
    private_directory(path.parent)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise WorkflowError("state target must be a regular non-symlink file")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def write_json(path: Path, value: object) -> None:
    atomic_write(path, canonical(value) + b"\n")


def write_artifact(root: Path, kind: str, value: object) -> tuple[Path, str]:
    content = canonical(value) + b"\n"
    content_digest = hashlib.sha256(content).hexdigest()
    directory = private_directory(root / "artifacts" / kind)
    path = directory / f"{content_digest}.json"
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            raise WorkflowError("immutable artifact conflict")
        return path.resolve(), content_digest
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    return path.resolve(), content_digest


def read_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise WorkflowError(f"{label} must be a regular non-symlink file")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"{label} must contain one JSON object") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"{label} must contain one JSON object")
    return value


def parse_url(value: str) -> dict[str, Any]:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise WorkflowError("source must be an exact HTTPS GitLab issue or collection URL")
    clean = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    issue_match = ISSUE_RE.fullmatch(clean)
    collection_match = COLLECTION_RE.fullmatch(clean)
    match = issue_match or collection_match
    if match is None or any(part in {"", ".", ".."} for part in match["project"].split("/")):
        raise WorkflowError("source must be an exact HTTPS GitLab issue or collection URL")
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    allowed = {
        "state",
        "label_name[]",
        "labels",
        "search",
        "assignee_username",
        "milestone_title",
    }
    if issue_match and query:
        raise WorkflowError("an exact GitLab issue URL must not contain a query")
    if set(query) - allowed or any(not entry for values in query.values() for entry in values):
        raise WorkflowError("collection URL contains an unsupported or empty filter")
    return {
        "url": value,
        "canonical_url": clean.rstrip("/"),
        "hostname": match["host"].lower(),
        "project_path": match["project"],
        "iid": int(issue_match["iid"]) if issue_match else None,
        "kind": "issue" if issue_match else "collection",
        "filters": query,
    }


def glab_json(hostname: str, endpoint: str) -> Any:
    if not re.fullmatch(r"[A-Za-z0-9._~%/?=&,+:-]+", endpoint) or ".." in endpoint:
        raise WorkflowError("generated GitLab endpoint is unsafe")
    command = ["glab", "api", "--hostname", hostname, "--method", "GET", endpoint]
    try:
        result = subprocess.run(  # noqa: S603 - validated argv, fixed executable, no shell
            command, check=False, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkflowError("GitLab GET failed") from exc
    if result.returncode != 0:
        raise WorkflowError("GitLab GET failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise WorkflowError("GitLab returned invalid JSON") from exc


def paginated(hostname: str, endpoint: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    separator = "&" if "?" in endpoint else "?"
    for page in range(1, MAX_PAGES + 1):
        value = glab_json(hostname, f"{endpoint}{separator}per_page=100&page={page}")
        if not isinstance(value, list):
            raise WorkflowError("paginated GitLab response must be a list")
        for raw in value:
            if not isinstance(raw, dict):
                raise WorkflowError("paginated GitLab item must be an object")
            identity = str(raw.get("id", digest(raw)))
            if identity not in seen:
                seen.add(identity)
                items.append(raw)
                if len(items) > MAX_ITEMS:
                    raise WorkflowError("GitLab collection exceeds the item limit")
        if len(value) < 100:
            return items
    raise WorkflowError("GitLab pagination exceeds the page limit")


def project_identity(target: dict[str, Any]) -> dict[str, Any]:
    encoded = urllib.parse.quote(target["project_path"], safe="")
    project = glab_json(target["hostname"], f"projects/{encoded}")
    if not isinstance(project, dict) or not isinstance(project.get("id"), int):
        raise WorkflowError("GitLab project identity is incomplete")
    return {
        "hostname": target["hostname"],
        "project_id": project["id"],
        "project_path": str(project.get("path_with_namespace") or target["project_path"]),
    }


def query_args(sources: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, str]:
    states = {value for source in sources for value in source["filters"].get("state", [])}
    if len(states) > 1 or (states and args.state != "opened" and args.state not in states):
        raise WorkflowError("collection sources contain conflicting state filters")
    state = next(iter(states), args.state)
    if state not in {"opened", "closed", "all"}:
        raise WorkflowError("collection state filter is unsupported")
    labels = set(args.label or [])
    for source in sources:
        for field in ("label_name[]", "labels"):
            for value in source["filters"].get(field, []):
                labels.update(part for part in value.split(",") if part)
    searches = {value for source in sources for value in source["filters"].get("search", [])}
    assignees = {
        value for source in sources for value in source["filters"].get("assignee_username", [])
    }
    milestones = {
        value for source in sources for value in source["filters"].get("milestone_title", [])
    }
    if len(searches) > 1 or len(assignees) > 1 or len(milestones) > 1:
        raise WorkflowError("collection sources contain conflicting filters")
    if args.search and searches and args.search not in searches:
        raise WorkflowError("collection sources contain conflicting search filters")
    if args.assignee and assignees and args.assignee not in assignees:
        raise WorkflowError("collection sources contain conflicting assignee filters")
    requested_milestone = getattr(args, "milestone", None)
    if requested_milestone and milestones and requested_milestone not in milestones:
        raise WorkflowError("collection sources contain conflicting milestone filters")
    result = {"state": state}
    if labels:
        result["labels"] = ",".join(sorted(labels))
    search = args.search or next(iter(searches), None)
    assignee = args.assignee or next(iter(assignees), None)
    milestone = requested_milestone or next(iter(milestones), None)
    if search:
        result["search"] = search
    if assignee:
        result["assignee_username"] = assignee
    if milestone:
        result["milestone"] = milestone
    return result


def issue_targets(sources: list[dict[str, Any]], filters: dict[str, str]) -> list[dict[str, Any]]:
    resolved_projects: dict[tuple[str, str], dict[str, Any]] = {}
    selected: dict[tuple[str, int, int], dict[str, Any]] = {}
    for source in sources:
        project_key = (source["hostname"], source["project_path"])
        project = resolved_projects.get(project_key)
        if project is None:
            project = project_identity(source)
            resolved_projects[project_key] = project
        if source["kind"] == "issue":
            iids = [source["iid"]]
        else:
            query = urllib.parse.urlencode(filters)
            listed = paginated(
                source["hostname"], f"projects/{project['project_id']}/issues?{query}"
            )
            iids = [item.get("iid") for item in listed]
        for iid in iids:
            if not isinstance(iid, int) or iid < 1:
                raise WorkflowError("GitLab issue identity is incomplete")
            key = (source["hostname"], project["project_id"], iid)
            selected[key] = {**project, "iid": iid}
    return [selected[key] for key in sorted(selected)]


def collect_issue(target: dict[str, Any]) -> dict[str, Any]:
    host, project_id, iid = target["hostname"], target["project_id"], target["iid"]
    base = f"projects/{project_id}/issues/{iid}"
    issue = glab_json(host, base)
    if not isinstance(issue, dict) or issue.get("iid") not in {None, iid}:
        raise WorkflowError("GitLab issue response is incomplete")
    discussions = paginated(host, f"{base}/discussions")
    links = paginated(host, f"{base}/links")
    merge_requests = paginated(host, f"{base}/related_merge_requests")
    closed_by = paginated(host, f"{base}/closed_by")
    mr_targets: dict[tuple[int, int], dict[str, Any]] = {}
    for merge_request in [*merge_requests, *closed_by]:
        project_value = merge_request.get("project_id")
        iid_value = merge_request.get("iid")
        if not positive(project_value) or not positive(iid_value):
            raise WorkflowError("related merge request identity is incomplete")
        mr_targets[(project_value, iid_value)] = merge_request
    mr_conversations = []
    for (mr_project_id, mr_iid), merge_request in sorted(mr_targets.items()):
        mr_conversations.append(
            {
                "project_id": mr_project_id,
                "iid": mr_iid,
                "web_url": str(merge_request.get("web_url") or ""),
                "discussions": paginated(
                    host,
                    f"projects/{mr_project_id}/merge_requests/{mr_iid}/discussions",
                ),
            }
        )
    source = {
        "target": target,
        "issue": issue,
        "discussions": discussions,
        "links": links,
        "merge_requests": merge_requests,
        "closed_by": closed_by,
        "merge_request_conversations": mr_conversations,
    }
    return {**source, "source_fingerprint": digest(source)}


def project_context(targets: list[dict[str, Any]]) -> dict[str, Any]:
    contexts: dict[str, Any] = {}
    users: dict[str, dict[str, Any]] = {}
    projects = {(item["hostname"], item["project_id"]): item for item in targets}
    for (hostname, project_id), target in sorted(projects.items()):
        if hostname not in users:
            user = glab_json(hostname, "user")
            if (
                not isinstance(user, dict)
                or not isinstance(user.get("id"), int)
                or not isinstance(user.get("username"), str)
                or not user["username"].strip()
            ):
                raise WorkflowError("authenticated GitLab user identity is incomplete")
            users[hostname] = {"id": user["id"], "username": user["username"]}
        issues = paginated(hostname, f"projects/{project_id}/issues?state=all")
        labels = paginated(hostname, f"projects/{project_id}/labels?include_ancestor_groups=true")
        active_milestones = paginated(
            hostname,
            f"projects/{project_id}/milestones?state=active&include_parent_milestones=true",
        )
        closed_milestones = paginated(
            hostname,
            f"projects/{project_id}/milestones?state=closed&include_parent_milestones=true",
        )
        releases = paginated(hostname, f"projects/{project_id}/releases")
        tags = paginated(hostname, f"projects/{project_id}/repository/tags")
        key = f"{hostname}:{project_id}"
        contexts[key] = {
            "project_path": target["project_path"],
            "current_user": users[hostname],
            "issues": issues,
            "labels": labels,
            "milestones": [
                {**item, "project_id": project_id}
                for item in [*active_milestones, *closed_milestones]
            ],
            "releases": releases,
            "tags": tags,
        }
    return contexts


def state_root(scope: dict[str, Any]) -> Path:
    home = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    return private_directory(home / "agent-skills" / "task-triage" / digest(scope)[:32])


def load_analysis_index(root: Path) -> dict[str, Any]:
    path = root / "analysis-index.json"
    if not path.exists():
        return {"items": {}}
    value = read_object(path, "analysis index")
    return value if isinstance(value.get("items"), dict) else {"items": {}}


def item_key(target: dict[str, Any]) -> str:
    return f"{target['hostname']}:{target['project_id']}:{target['iid']}"


def collect(args: argparse.Namespace) -> dict[str, Any]:
    if not args.source:
        raise WorkflowError("at least one --source is required")
    sources = [parse_url(value) for value in args.source]
    filters = query_args(sources, args)
    locale = getattr(args, "locale", "en")
    if locale not in TEXT:
        raise WorkflowError("locale must be en or ru")
    scope = {
        "sources": sorted(source["canonical_url"] for source in sources),
        "filters": filters,
        "locale": locale,
    }
    root = state_root(scope)
    targets = issue_targets(sources, filters)
    if not targets:
        raise WorkflowError("the selected GitLab collection is empty")
    context = project_context(targets)
    context_digest = digest(context)
    analysis_index = load_analysis_index(root)["items"]
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for target in targets:
        try:
            evidence = collect_issue(target)
            artifact, evidence_digest = write_artifact(root, "evidence", evidence)
            cached = analysis_index.get(item_key(target))
            reusable = (
                isinstance(cached, dict)
                and cached.get("source_fingerprint") == evidence["source_fingerprint"]
                and cached.get("context_digest") == context_digest
                and isinstance(cached.get("analysis"), dict)
            )
            items.append(
                {
                    "target": target,
                    "url": str(evidence["issue"].get("web_url") or ""),
                    "evidence_path": str(artifact),
                    "evidence_digest": evidence_digest,
                    "source_fingerprint": evidence["source_fingerprint"],
                    "context_digest": context_digest,
                    "analysis_required": not reusable,
                    "cached_analysis": cached.get("analysis") if reusable else None,
                }
            )
        except WorkflowError as exc:
            errors.append({"target": item_key(target), "message": str(exc)})
    payload = {
        "schema": "task-triage/collection-evidence/v2",
        "created_at": datetime.now(UTC).isoformat(),
        "scope": scope,
        "context": context,
        "context_digest": context_digest,
        "items": items,
        "errors": errors,
        "complete": not errors and len(items) == len(targets),
        "external_mutations": False,
    }
    artifact, artifact_digest = write_artifact(root, "collection", payload)
    pointer = {
        "schema": "task-triage/current/v2",
        "collection_path": str(artifact),
        "collection_digest": artifact_digest,
        "context_digest": context_digest,
    }
    write_json(root / "current.json", pointer)
    return {
        "status": "ok" if payload["complete"] else "partial",
        "artifact_root": str(root),
        **pointer,
        "items": items,
        "errors": errors,
        "external_mutations": False,
    }


def resolve_collection(path: Path) -> tuple[dict[str, Any], str, Path]:
    pointer = read_object(path, "collection pointer")
    digest_value = pointer.get("collection_digest")
    artifact_value = pointer.get("collection_path")
    if not isinstance(digest_value, str) or not DIGEST_RE.fullmatch(digest_value):
        raise WorkflowError("collection pointer digest is invalid")
    if not isinstance(artifact_value, str):
        raise WorkflowError("collection pointer path is invalid")
    artifact = Path(artifact_value)
    expected = path.parent.resolve() / "artifacts" / "collection" / f"{digest_value}.json"
    if (
        artifact.resolve() != expected
        or artifact.is_symlink()
        or artifact.name != f"{digest_value}.json"
        or hashlib.sha256(artifact.read_bytes()).hexdigest() != digest_value
    ):
        raise WorkflowError("collection pointer binding is invalid")
    collection = read_object(artifact, "collection artifact")
    if collection.get("schema") != "task-triage/collection-evidence/v2":
        raise WorkflowError("collection artifact schema is invalid")
    return collection, digest_value, path.parent.resolve()


def text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowError(f"{label} must be non-empty text")
    return value.strip()


def positive(value: object) -> TypeGuard[int]:
    return type(value) is int and value > 0


def conversation_for(
    snapshot: dict[str, Any], target: object, label: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(target, dict):
        raise WorkflowError(f"{label} target must be an object")
    kind = target.get("kind")
    project_id = target.get("project_id")
    iid = target.get("iid")
    discussion_id = target.get("discussion_id")
    if kind not in {"issue", "merge_request"} or not positive(project_id) or not positive(iid):
        raise WorkflowError(f"{label} target identity is invalid")
    if discussion_id is not None and (
        not isinstance(discussion_id, str) or not discussion_id.strip()
    ):
        raise WorkflowError(f"{label} discussion identity is invalid")
    if kind == "issue":
        observed = snapshot["target"]
        if project_id != observed["project_id"] or iid != observed["iid"]:
            raise WorkflowError(f"{label} issue target was not observed")
        discussions = snapshot.get("discussions", [])
    else:
        conversations = snapshot.get("merge_request_conversations", [])
        match = next(
            (
                item
                for item in conversations
                if item.get("project_id") == project_id and item.get("iid") == iid
            ),
            None,
        )
        if match is None:
            raise WorkflowError(f"{label} merge request target was not observed")
        discussions = match.get("discussions", [])
    if not isinstance(discussions, list):
        raise WorkflowError(f"{label} discussions are invalid")
    if discussion_id is not None and not any(
        isinstance(discussion, dict) and str(discussion.get("id")) == discussion_id
        for discussion in discussions
    ):
        raise WorkflowError(f"{label} discussion was not observed")
    normalized = {
        "kind": kind,
        "project_id": project_id,
        "iid": iid,
        "discussion_id": discussion_id,
    }
    return normalized, discussions


def discussion_notes(
    discussions: list[dict[str, Any]], discussion_id: str | None
) -> list[dict[str, Any]]:
    notes: list[dict[str, Any]] = []
    for discussion in discussions:
        if not isinstance(discussion, dict) or (
            discussion_id is not None and str(discussion.get("id")) != discussion_id
        ):
            continue
        raw_notes = discussion.get("notes", [])
        if isinstance(raw_notes, list):
            notes.extend(note for note in raw_notes if isinstance(note, dict))
    return sorted(notes, key=lambda note: (str(note.get("created_at") or ""), str(note.get("id"))))


def validate_message(snapshot: dict[str, Any], value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"target", "body"}:
        raise WorkflowError(f"{label} must contain target and body")
    target, _ = conversation_for(snapshot, value["target"], label)
    return {"target": target, "body": text(value["body"], f"{label} body")}


def validate_information_request(
    snapshot: dict[str, Any], current_user: dict[str, Any], value: object, label: str
) -> dict[str, Any]:
    expected = {"action", "target", "body", "prior_note_ids", "rationale"}
    if not isinstance(value, dict) or set(value) != expected:
        raise WorkflowError(f"{label} fields are invalid")
    action = value["action"]
    if action not in INFORMATION_ACTIONS:
        raise WorkflowError(f"{label} action is invalid")
    rationale = text(value["rationale"], f"{label} rationale")
    if action == "none":
        if (
            value["target"] is not None
            or value["body"] is not None
            or value["prior_note_ids"] != []
        ):
            raise WorkflowError(f"{label} with no action must not contain publication data")
        return {
            "action": action,
            "target": None,
            "body": None,
            "prior_note_ids": [],
            "rationale": rationale,
        }
    target, discussions = conversation_for(snapshot, value["target"], label)
    if target["kind"] == "issue":
        issue = snapshot.get("issue")
        if not isinstance(issue, dict) or issue.get("state") != "opened":
            raise WorkflowError(f"{label} target issue is not open")
    body = text(value["body"], f"{label} body")
    prior_note_ids = value["prior_note_ids"]
    required = {"new": 0, "ping_1": 1, "ping_2": 2, "close": 3}[action]
    if action != "new" and target["discussion_id"] is None:
        raise WorkflowError(f"{label} follow-up must target the observed discussion")
    if (
        not isinstance(prior_note_ids, list)
        or len(prior_note_ids) != required
        or not all(positive(note_id) for note_id in prior_note_ids)
        or len(set(prior_note_ids)) != len(prior_note_ids)
    ):
        raise WorkflowError(f"{label} does not follow the information-request sequence")
    if action == "close" and target["kind"] != "issue":
        raise WorkflowError(f"{label} may close only an issue")
    notes = discussion_notes(discussions, target["discussion_id"])
    if action == "new" and target["discussion_id"] is not None:
        latest = next((note for note in reversed(notes) if note.get("system") is not True), None)
        author = latest.get("author") if isinstance(latest, dict) else None
        if not isinstance(author, dict) or author.get("id") == current_user["id"]:
            raise WorkflowError(
                f"{label} new cycle in an existing discussion requires a latest participant reply"
            )
    positions = {note.get("id"): index for index, note in enumerate(notes)}
    if any(note_id not in positions for note_id in prior_note_ids) or any(
        positions[left] >= positions[right] for left, right in pairwise(prior_note_ids)
    ):
        raise WorkflowError(f"{label} prior notes were not observed in order")
    current_id = current_user["id"]
    for note_id in prior_note_ids:
        note = notes[positions[note_id]]
        author = note.get("author")
        if not isinstance(author, dict) or author.get("id") != current_id:
            raise WorkflowError(f"{label} prior notes were not authored by the current user")
    if prior_note_ids:
        for note in notes[positions[prior_note_ids[-1]] + 1 :]:
            if note.get("system") is True:
                continue
            raise WorkflowError(f"{label} has a later note that must be assessed")
        last_other_note = -1
        for index, note in enumerate(notes[: positions[prior_note_ids[-1]] + 1]):
            if note.get("system") is True:
                continue
            author = note.get("author")
            if not isinstance(author, dict) or author.get("id") != current_id:
                last_other_note = index
        cycle_ids = [
            note.get("id")
            for note in notes[last_other_note + 1 : positions[prior_note_ids[-1]] + 1]
            if note.get("system") is not True
        ]
        if cycle_ids != prior_note_ids:
            raise WorkflowError(f"{label} prior notes are not the complete latest cycle")
    return {
        "action": action,
        "target": target,
        "body": body,
        "prior_note_ids": prior_note_ids,
        "rationale": rationale,
    }


def validate_proposed_changes(snapshot: dict[str, Any], value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict) or set(value) - {
        "title",
        "description",
        "labels",
        "links",
        "messages",
    }:
        raise WorkflowError("proposed changes contain unsupported fields")
    result: dict[str, Any] = {}
    if "title" in value:
        title = text(value["title"], "proposed title")
        if "\n" in title or "\r" in title:
            raise WorkflowError("proposed title must be one line")
        result["title"] = title
    if "description" in value:
        result["description"] = text(value["description"], "proposed description")
    if "labels" in value:
        labels = value["labels"]
        if not isinstance(labels, list) or not all(
            isinstance(label, str) and label.strip() and "," not in label for label in labels
        ):
            raise WorkflowError("proposed labels are invalid")
        result["labels"] = [label.strip() for label in labels]
    links = value.get("links", [])
    if not isinstance(links, list):
        raise WorkflowError("proposed links must be a list")
    for link in links:
        if (
            not isinstance(link, dict)
            or not positive(link.get("target_project_id"))
            or not positive(link.get("target_issue_iid"))
            or link.get("link_type") not in {"relates_to", "blocks", "is_blocked_by"}
        ):
            raise WorkflowError("proposed issue link is invalid")
    if links:
        result["links"] = links
    messages = value.get("messages", [])
    if not isinstance(messages, list):
        raise WorkflowError("proposed messages must be a list")
    if messages:
        result["messages"] = [
            validate_message(snapshot, message, f"proposed messages[{index}]")
            for index, message in enumerate(messages)
        ]
    return result


def validate_analysis(collection: dict[str, Any], analysis: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = analysis.get("items")
    if not isinstance(raw_items, list):
        raise WorkflowError("analysis items must be a list")
    evidence = {item["evidence_digest"]: item for item in collection["items"]}
    if len(raw_items) != len(evidence):
        raise WorkflowError("analysis must contain every collected issue exactly once")
    seen: set[str] = set()
    request_targets: set[tuple[str, str, int, int, str | None]] = set()
    result: list[dict[str, Any]] = []
    for position, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise WorkflowError("analysis item must be an object")
        evidence_digest = text(raw.get("evidence_digest"), f"items[{position}].evidence_digest")
        if evidence_digest not in evidence or evidence_digest in seen:
            raise WorkflowError("analysis evidence binding is missing or duplicated")
        seen.add(evidence_digest)
        actuality = raw.get("actuality")
        quality = raw.get("quality")
        if not isinstance(actuality, dict) or actuality.get("status") not in ACTUALITY:
            raise WorkflowError("analysis actuality is invalid")
        if not isinstance(quality, dict) or quality.get("verdict") not in VERDICTS:
            raise WorkflowError("analysis quality verdict is invalid")
        for field in ("severity", "priority"):
            text(raw.get(field), f"items[{position}].{field}")
        evidence_item = evidence[evidence_digest]
        target = evidence_item["target"]
        context = collection["context"].get(f"{target['hostname']}:{target['project_id']}")
        if not isinstance(context, dict) or not isinstance(context.get("milestones"), list):
            raise WorkflowError("analysis milestone catalog is unavailable")
        snapshot = read_object(Path(evidence_item["evidence_path"]), "issue evidence")
        current = snapshot["issue"].get("milestone")
        current_id = current.get("id") if isinstance(current, dict) else None
        try:
            release_plan = validate_release_plan(
                raw.get("release_plan"),
                quality_verdict=quality["verdict"],
                milestone_catalog=context["milestones"],
                current_milestone_id=current_id if isinstance(current_id, int) else None,
            )
        except PlanningError as exc:
            raise WorkflowError(f"analysis release plan is invalid: {exc}") from exc
        if release_plan["decision"]["status"] == "accepted" and actuality["status"] != "current":
            raise WorkflowError("only a current issue may be accepted")
        proposed_changes = validate_proposed_changes(snapshot, raw.get("proposed_changes"))
        requests = raw.get("information_requests", [])
        if not isinstance(requests, list):
            raise WorkflowError("information requests must be a list")
        current_user = context.get("current_user")
        if not isinstance(current_user, dict):
            raise WorkflowError("authenticated GitLab user evidence is unavailable")
        information_requests = [
            validate_information_request(
                snapshot,
                current_user,
                request,
                f"information_requests[{index}]",
            )
            for index, request in enumerate(requests)
        ]
        for request in information_requests:
            if request["action"] == "none":
                continue
            request_target = request["target"]
            request_key = (
                target["hostname"],
                request_target["kind"],
                request_target["project_id"],
                request_target["iid"],
                request_target["discussion_id"],
            )
            if request_key in request_targets:
                raise WorkflowError("analysis contains multiple information actions for one target")
            request_targets.add(request_key)
        result.append(
            {
                **raw,
                "release_plan": release_plan,
                "proposed_changes": proposed_changes,
                "information_requests": information_requests,
                "evidence": evidence_item,
            }
        )
    return result


def markdown_list(value: object, locale: str) -> str:
    if not isinstance(value, list) or not value:
        return f"- {TEXT[locale]['none']}"
    return "\n".join(f"- {item}" for item in value)


def display(value: object, locale: str, field: str) -> str:
    translations = RU_VALUES.get(field, {})
    if locale == "ru" and (value is None or isinstance(value, str)) and value in translations:
        return translations[value]
    return str(value)


def api_command(host: str, method: str, endpoint: str, request: Path) -> str:
    return shlex.join(
        [
            "glab",
            "api",
            "--hostname",
            host,
            "--method",
            method,
            endpoint,
            "--silent",
            "--header",
            "Content-Type: application/json",
            "--input",
            str(request),
        ]
    )


def code_block(content: str, language: str) -> list[str]:
    fence = "`" * max(3, max((len(match) + 1 for match in re.findall(r"`+", content)), default=3))
    return [f"{fence}{language}", content, fence]


def action(
    root: Path,
    host: str,
    kind: str,
    method: str,
    endpoint: str,
    payload: dict[str, Any],
    preview: str,
) -> dict[str, str]:
    request, _ = write_artifact(root, "commands", payload)
    return {
        "kind": kind,
        "preview": preview,
        "command": api_command(host, method, endpoint, request),
    }


def message_action(
    root: Path, host: str, target: dict[str, Any], body: str, kind: str = "message"
) -> dict[str, str]:
    collection = "issues" if target["kind"] == "issue" else "merge_requests"
    endpoint = f"projects/{target['project_id']}/{collection}/{target['iid']}"
    if target["discussion_id"] is None:
        endpoint += "/notes"
    else:
        encoded = urllib.parse.quote(target["discussion_id"], safe="")
        endpoint += f"/discussions/{encoded}/notes"
    return action(root, host, kind, "POST", endpoint, {"body": body}, body)


def commands_for(root: Path, item: dict[str, Any]) -> list[dict[str, str]]:
    proposed = item["proposed_changes"]
    target = item["evidence"]["target"]
    host, project_id, iid = target["hostname"], target["project_id"], target["iid"]
    issue_endpoint = f"projects/{project_id}/issues/{iid}"
    commands: list[dict[str, str]] = []
    for field, kind in (
        ("title", "title"),
        ("description", "description"),
        ("labels", "labels"),
    ):
        if field not in proposed:
            continue
        value = proposed[field]
        payload_value = ",".join(value) if field == "labels" else value
        preview = json.dumps({field: value}, ensure_ascii=False, indent=2)
        commands.append(
            action(root, host, kind, "PUT", issue_endpoint, {field: payload_value}, preview)
        )
    release_plan = item["release_plan"]
    decision = release_plan["decision"]["status"]
    milestone = release_plan["milestone"]
    if decision == "accepted" and milestone["status"] == "create":
        title = milestone["candidate"]["title"]
        commands.append(
            action(
                root,
                host,
                "create_milestone",
                "POST",
                f"projects/{project_id}/milestones",
                {"title": title},
                title,
            )
        )
    if decision == "accepted" and milestone["status"] == "selected":
        milestone_id = milestone["candidate"]["id"]
        commands.append(
            action(
                root,
                host,
                "milestone",
                "PUT",
                issue_endpoint,
                {"milestone_id": milestone_id},
                str(milestone["candidate"]["title"]),
            )
        )
    elif decision != "accepted" and milestone["status"] == "remove":
        commands.append(
            action(
                root,
                host,
                "milestone",
                "PUT",
                issue_endpoint,
                {"milestone_id": 0},
                json.dumps({"milestone_id": 0}, indent=2),
            )
        )
    for link in proposed.get("links", []):
        commands.append(
            action(
                root,
                host,
                "link",
                "POST",
                f"{issue_endpoint}/links",
                link,
                json.dumps(link, ensure_ascii=False, indent=2),
            )
        )
    for message in proposed.get("messages", []):
        commands.append(message_action(root, host, message["target"], message["body"]))
    for request in item["information_requests"]:
        if request["action"] == "none":
            continue
        commands.append(
            message_action(
                root,
                host,
                request["target"],
                request["body"],
                f"information_{request['action']}",
            )
        )
        if request["action"] == "close":
            request_target = request["target"]
            endpoint = f"projects/{request_target['project_id']}/issues/{request_target['iid']}"
            commands.append(
                action(
                    root,
                    host,
                    "close",
                    "PUT",
                    endpoint,
                    {"state_event": "close"},
                    request["rationale"],
                )
            )
    return commands


def item_markdown(item: dict[str, Any], commands: list[dict[str, str]], locale: str) -> str:
    evidence = item["evidence"]
    issue = read_object(Path(evidence["evidence_path"]), "issue evidence")["issue"]
    actuality, quality = item["actuality"], item["quality"]
    release_plan = item["release_plan"]
    semver = release_plan["semver"]
    labels = TEXT[locale]
    sections = [
        f"# {issue.get('title', evidence['url'])}",
        "",
        f"- {labels['source']}: {evidence['url']}",
        f"- {labels['actuality']}: {display(actuality['status'], locale, 'actuality')}",
        f"- {labels['quality']}: {display(quality['verdict'], locale, 'quality')}",
        f"- {labels['decision']}: {display(release_plan['decision']['status'], locale, 'decision')}",
        f"- {labels['planning']}: {display(release_plan['planning_verdict'], locale, 'planning')}",
        f"- SemVer: {semver['level']}",
        f"- {labels['release']}: {display(release_plan['release']['target_version'], locale, 'release')}",
        f"- {labels['milestone']}: {display(release_plan['milestone']['status'], locale, 'milestone')}",
        f"- {labels['severity']}: {item['severity']}",
        f"- {labels['priority']}: {item['priority']}",
        "",
        f"## {labels['actuality']}",
        "",
        text(actuality.get("rationale"), "actuality rationale"),
        "",
        f"## {labels['quality_findings']}",
        "",
        markdown_list(quality.get("findings"), locale),
        "",
        f"## {labels['relations']}",
        "",
        markdown_list(item.get("duplicates"), locale),
        "",
        markdown_list(item.get("related_issues"), locale),
        "",
        f"## {labels['merge_requests']}",
        "",
        markdown_list(item.get("merge_requests"), locale),
        "",
        "## SemVer",
        "",
        text(semver.get("rationale"), "SemVer rationale"),
        "",
        f"## {labels['release_planning']}",
        "",
        text(release_plan["decision"].get("rationale"), "decision rationale"),
        "",
        text(release_plan["milestone"].get("rationale"), "milestone rationale"),
        "",
        f"## {labels['recommendations']}",
        "",
        markdown_list(item.get("recommendations"), locale),
        "",
        f"## {labels['commands']}",
        "",
    ]
    if commands:
        for command in commands:
            sections.extend(
                [
                    f"### {labels['action_' + command['kind']]}",
                    "",
                    f"**{labels['preview']}**",
                    "",
                    *code_block(command["preview"], "text"),
                    "",
                    f"**{labels['command']}**",
                    "",
                    *code_block(command["command"], "sh"),
                    "",
                ]
            )
    else:
        sections.append(labels["no_changes"])
    return "\n".join(sections) + "\n"


def publish(args: argparse.Namespace) -> dict[str, Any]:
    collection, collection_digest, root = resolve_collection(Path(args.collection).resolve())
    locale = collection.get("scope", {}).get("locale")
    if locale not in TEXT:
        raise WorkflowError("collection locale is invalid")
    labels = TEXT[locale]
    analysis = read_object(Path(args.analysis).resolve(), "triage analysis")
    if analysis.get("collection_digest") != collection_digest:
        raise WorkflowError("analysis is stale for the selected collection")
    items = validate_analysis(collection, analysis)
    reports = private_directory(root / "reports")
    report_entries: list[dict[str, str]] = []
    analysis_index = load_analysis_index(root)["items"]
    for item in items:
        commands = commands_for(root, item)
        target = item["evidence"]["target"]
        report = reports / f"{target['hostname']}-{target['project_id']}-{target['iid']}.md"
        atomic_write(report, item_markdown(item, commands, locale).encode())
        report_entries.append({"url": item["evidence"]["url"], "report": str(report)})
        cached_analysis = {key: value for key, value in item.items() if key != "evidence"}
        cached_analysis["release_plan"] = {
            key: item["release_plan"][key] for key in ("decision", "semver", "release", "milestone")
        }
        analysis_index[item_key(target)] = {
            "source_fingerprint": item["evidence"]["source_fingerprint"],
            "context_digest": item["evidence"]["context_digest"],
            "analysis": cached_analysis,
        }
    artifact_value = {
        "schema": "task-triage/analysis/v2",
        "created_at": datetime.now(UTC).isoformat(),
        "collection_digest": collection_digest,
        "items": [
            {key: value for key, value in item.items() if key != "evidence"} for item in items
        ],
        "top_five": analysis.get("top_five", []),
        "parallel_groups": analysis.get("parallel_groups", []),
        "questions": analysis.get("questions", []),
        "external_mutations": False,
    }
    planning_complete = all(item["release_plan"]["planning_verdict"] == "ready" for item in items)
    pending_requests = any(
        request["action"] != "none" for item in items for request in item["information_requests"]
    )
    complete = (
        collection["complete"]
        and not artifact_value["questions"]
        and planning_complete
        and not pending_requests
    )
    artifact, analysis_digest = write_artifact(root, "analysis", artifact_value)
    write_json(root / "analysis-index.json", {"items": analysis_index})
    summary_lines = [
        f"# {labels['summary']}",
        "",
        f"- {labels['status']}: {labels['complete'] if complete else labels['partial']}",
        f"- {labels['collection']}: `{collection_digest}`",
        f"- {labels['analysis']}: `{analysis_digest}`",
        "",
        f"## {labels['first']}",
        "",
        markdown_list(artifact_value["top_five"][:5], locale),
        "",
        f"## {labels['parallel']}",
        "",
        markdown_list(artifact_value["parallel_groups"], locale),
        "",
        f"## {labels['questions']}",
        "",
        markdown_list(artifact_value["questions"], locale),
        "",
        f"## {labels['reports']}",
        "",
        *[f"- {entry['report']}" for entry in report_entries],
        "",
    ]
    summary = root / "triage-summary.md"
    atomic_write(summary, "\n".join(summary_lines).encode())
    write_json(
        root / "analysis-current.json",
        {
            "analysis_path": str(artifact),
            "analysis_digest": analysis_digest,
            "collection_digest": collection_digest,
            "summary": str(summary),
        },
    )
    return {
        "status": "ok" if complete else "partial",
        "summary": str(summary),
        "analysis_path": str(artifact),
        "analysis_digest": analysis_digest,
        "reports": report_entries,
        "external_mutations": False,
    }


def parser() -> Parser:
    cli = Parser(prog="triage-gitlab")
    cli.add_argument("--capabilities", action="store_true")
    subparsers = cli.add_subparsers(dest="command")
    collect_parser = subparsers.add_parser("collect")
    collect_parser.add_argument("--source", action="append")
    collect_parser.add_argument("--state", choices=("opened", "closed", "all"), default="opened")
    collect_parser.add_argument("--label", action="append")
    collect_parser.add_argument("--search")
    collect_parser.add_argument("--assignee")
    collect_parser.add_argument("--milestone")
    collect_parser.add_argument("--locale", choices=("en", "ru"), default="en")
    publish_parser = subparsers.add_parser("publish")
    publish_parser.add_argument("--collection", required=True)
    publish_parser.add_argument("--analysis", required=True)
    return cli


def run(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        if args.capabilities:
            print(
                json.dumps(
                    {
                        "schema_version": 1,
                        "payload_version": "2.0.0",
                        "input": ["gitlab-issue", "gitlab-issue-list", "gitlab-collection"],
                        "mutation": "private-local-write",
                        "external_mutations": False,
                    },
                    sort_keys=True,
                )
            )
            return 0
        if args.command is None:
            raise WorkflowError("a command is required")
        result = collect(args) if args.command == "collect" else publish(args)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] == "ok" else 1
    except (OSError, UnicodeError, WorkflowError) as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": {"code": "triage_failed", "message": str(exc)},
                    "external_mutations": False,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
