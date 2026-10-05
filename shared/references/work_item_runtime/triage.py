#!/usr/bin/env python3
"""Collect and persist bounded GitLab task-triage evidence and reports."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shlex
import subprocess
import tempfile
import urllib.parse
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn, TypeGuard, cast

from .release_planning import PlanningError
from .release_planning import validate as validate_release_plan

if TYPE_CHECKING:
    from ..state_artifacts import (
        ensure_private_directory,
        versioned_markdown,
        xdg_state_home,
    )
else:
    try:
        from ..state_artifacts import (
            ensure_private_directory,
            versioned_markdown,
            xdg_state_home,
        )
    except ImportError:
        from .state_artifacts import (
            ensure_private_directory,
            versioned_markdown,
            xdg_state_home,
        )

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
INFORMATION_ACTIONS = {"none", "new", "ping_1", "ping_2", "close", "close_fixed"}
CONFIDENCE = {"low", "medium", "high"}
DECISIONS = ("accepted", "deferred", "rejected", "duplicate", "obsolete")
ANALYSIS_INDEX_SCHEMA = "task-triage/analysis-index/v4"
TEXT = {
    "en": {
        "summary": "Task triage summary",
        "analysis_status": "Analysis status",
        "follow_up_status": "Follow-up status",
        "complete": "complete",
        "partial": "partial",
        "clear": "clear",
        "pending": "pending",
        "collection_errors": "Collection errors",
        "unanswered_questions": "Unanswered user questions",
        "planning_pending": "Non-ready planning",
        "requests_pending": "Information requests to publish",
        "request_issues": "Affected issues",
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
        "duplicates": "Duplicates",
        "issue_relations": "Issue relations",
        "relation_existing": "existing link",
        "relation_proposed": "link proposed",
        "merge_requests": "Merge requests",
        "release_planning": "Release planning",
        "recommendations": "Recommendations",
        "recommendation": "Agent recommendation",
        "proposal": "Primary proposal",
        "rationale": "Rationale",
        "assumptions": "Assumptions",
        "confidence": "Confidence",
        "alternatives": "Alternatives",
        "reconsider_if": "Reconsider if",
        "reason": "Reason",
        "next_step": "Next step",
        "why_now": "Why now",
        "question_evidence": "Evidence",
        "missing_decision": "Decision needed",
        "planning_effect": "Planning effect",
        "options": "Options",
        "fallback": "Fallback",
        "report": "Report",
        "decision_accepted": "Accepted",
        "decision_accepted_ready": "Fully planned",
        "decision_accepted_pending": "Awaiting planning action",
        "decision_deferred": "Deferred",
        "decision_rejected": "Rejected",
        "decision_duplicate": "Duplicates",
        "decision_obsolete": "Obsolete",
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
        "action_replace_link": "Replace conflicting issue link",
        "action_replace_link_delete": "Delete conflicting issue link",
        "action_replace_link_create": "Create replacement issue link",
        "action_message": "Publish message",
        "action_information_new": "Publish information request",
        "action_information_ping_1": "Publish first follow-up",
        "action_information_ping_2": "Publish second follow-up",
        "action_information_close": "Publish stale closure message",
        "action_information_close_fixed": "Publish quietly-fixed closure message",
        "action_close": "Close issue",
        "guard_user": "Verify the authenticated user still matches the triage snapshot",
        "guard_user_stop": "authenticated GitLab user changed; regenerate the triage plan",
        "guard_open_mr": "Verify no open merge request already references this issue",
        "guard_open_mr_stop": "an open merge request references this issue; assess it and propose it instead of closing the issue or assigning a milestone",
        "guard_fresh": "Verify the target is unchanged since triage",
        "guard_fresh_stop": "the target changed after triage; refresh the analysis and regenerate the plan",
        "guard_open": "Verify the target is still open",
        "guard_open_stop": "the target is closed; refresh the analysis and regenerate the plan",
        "guard_title": "Verify the title is unchanged since triage",
        "guard_title_stop": "the title changed after triage; refresh the analysis and regenerate the plan",
        "guard_description": "Verify the description is unchanged since triage",
        "guard_description_stop": "the description changed after triage; refresh the analysis and regenerate the plan",
        "guard_labels": "Verify the labels still match the triage snapshot",
        "guard_labels_stop": "labels changed after triage; refresh the analysis and regenerate the plan",
        "guard_milestone": "Verify the milestone still matches the triage snapshot",
        "guard_milestone_stop": "the milestone changed after triage; refresh the analysis and regenerate the plan",
        "guard_conversation": "Verify the conversation is unchanged and the prepared message is not published yet",
        "guard_conversation_stop": "the conversation changed or the message is already published; refresh the analysis and regenerate the plan",
        "guard_links": "Verify the observed issue links are unchanged",
        "guard_links_stop": "issue links changed after triage; refresh the analysis and regenerate the plan",
        "guard_milestone_search": "Find the proposed milestone or create it when absent",
        "regenerate": "Regeneration required",
        "uncovered": "Actions without commands",
    },
    "ru": {
        "summary": "Сводка триажа задач",
        "analysis_status": "Статус анализа",
        "follow_up_status": "Статус дальнейших действий",
        "complete": "завершён",
        "partial": "частичный",
        "clear": "действия не требуются",
        "pending": "требуются действия",
        "collection_errors": "Ошибки сбора",  # noqa: RUF001
        "unanswered_questions": "Неотвеченные вопросы пользователю",
        "planning_pending": "Неготовое планирование",
        "requests_pending": "Запросы информации к публикации",
        "request_issues": "Затронутые задачи",
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
        "duplicates": "Дубликаты",
        "issue_relations": "Связи с задачами",  # noqa: RUF001
        "relation_existing": "связь существует",
        "relation_proposed": "связь предложена",
        "merge_requests": "Связанные MR",
        "release_planning": "Планирование релиза",
        "recommendations": "Рекомендации",
        "recommendation": "Рекомендация агента",
        "proposal": "Основной вариант",
        "rationale": "Обоснование",
        "assumptions": "Допущения",
        "confidence": "Уверенность",
        "alternatives": "Альтернативы",
        "reconsider_if": "Пересмотреть, если",
        "reason": "Причина",
        "next_step": "Следующий шаг",
        "why_now": "Почему сейчас",
        "question_evidence": "Факты",
        "missing_decision": "Требуемое решение",
        "planning_effect": "Влияние на планирование",
        "options": "Варианты",
        "fallback": "Следующее обращение",
        "report": "Отчёт",
        "decision_accepted": "Приняты",
        "decision_accepted_ready": "Полностью распланированы",
        "decision_accepted_pending": "Ожидают действия по планированию",
        "decision_deferred": "Отложены",
        "decision_rejected": "Отклонены",
        "decision_duplicate": "Дубликаты",
        "decision_obsolete": "Устарели",
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
        "action_replace_link": "Заменить конфликтующую связь задач",
        "action_replace_link_delete": "Удалить конфликтующую связь задач",
        "action_replace_link_create": "Создать заменяющую связь задач",
        "action_message": "Опубликовать сообщение",
        "action_information_new": "Опубликовать запрос информации",
        "action_information_ping_1": "Опубликовать первый пинг",
        "action_information_ping_2": "Опубликовать второй пинг",
        "action_information_close": "Опубликовать финальное сообщение",
        "action_information_close_fixed": "Опубликовать закрытие «тихо исправлено»",
        "action_close": "Закрыть задачу",
        "guard_user": "Проверить, что аутентифицированный пользователь совпадает со снимком триажа",  # noqa: RUF001
        "guard_user_stop": "пользователь GitLab изменился; перегенерируйте план триажа",
        "guard_open_mr": "Проверить, что открытый MR ещё не ссылается на эту задачу",
        "guard_open_mr_stop": "существует открытый MR, ссылающийся на задачу; разберите его вместо закрытия задачи или назначения майлстоуна",  # noqa: RUF001
        "guard_fresh": "Проверить, что цель не изменилась после триажа",
        "guard_fresh_stop": "цель изменилась после триажа; обновите анализ и перегенерируйте план",
        "guard_open": "Проверить, что цель всё ещё открыта",
        "guard_open_stop": "цель закрыта; обновите анализ и перегенерируйте план",
        "guard_title": "Проверить, что заголовок не изменился после триажа",
        "guard_title_stop": "заголовок изменился после триажа; обновите анализ и перегенерируйте план",
        "guard_description": "Проверить, что описание не изменилось после триажа",
        "guard_description_stop": "описание изменилось после триажа; обновите анализ и перегенерируйте план",
        "guard_labels": "Проверить, что метки совпадают со снимком триажа",  # noqa: RUF001
        "guard_labels_stop": "метки изменились после триажа; обновите анализ и перегенерируйте план",
        "guard_milestone": "Проверить, что майлстоун совпадает со снимком триажа",  # noqa: RUF001
        "guard_milestone_stop": "майлстоун изменился после триажа; обновите анализ и перегенерируйте план",
        "guard_conversation": "Проверить, что обсуждение не изменилось и сообщение ещё не опубликовано",
        "guard_conversation_stop": "обсуждение изменилось или сообщение уже опубликовано; обновите анализ и перегенерируйте план",
        "guard_links": "Проверить, что наблюдаемые связи задач не изменились",
        "guard_links_stop": "связи задач изменились после триажа; обновите анализ и перегенерируйте план",
        "guard_milestone_search": "Найти предложенный майлстоун или создать его при отсутствии",  # noqa: RUF001
        "regenerate": "Требуется перегенерация",
        "uncovered": "Действия без команд",
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
    try:
        return ensure_private_directory(path, xdg_state_home())
    except (OSError, ValueError) as error:
        raise WorkflowError("state directory must be a private real directory") from error


def _drop_issue_memory(target: dict[str, Any], title: str, decision: str, reason: str) -> None:
    """Queue a per-issue triage decision into the memomatic inbox; advisory only."""
    try:
        inbox_path = Path(__file__).with_name("memomatic_inbox.py")
        if not inbox_path.exists():
            inbox_path = next(
                parent / "memomatic_inbox.py"
                for parent in Path(__file__).resolve().parents
                if (parent / "memomatic_inbox.py").is_file()
            )
        spec = importlib.util.spec_from_file_location("memomatic_inbox", inbox_path)
        if spec is None or spec.loader is None:
            return
        inbox = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inbox)
        hostname = str(target.get("hostname", "")).lower().replace(".", "-")
        lines = inbox.entry_lines(
            [
                (
                    f"triage {target.get('hostname')}/{target.get('project_id')}#{target.get('iid')}"
                    f" \u00ab{title}\u00bb: {decision} \u2014 {reason}"
                )
            ],
            source="task-triage",
            key=f"triage-{hostname}-{target.get('project_id')}-{target.get('iid')}",
        )
        inbox.drop_memory(lines, "task-triage")
    except Exception:
        return


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
        fsync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)


def fsync_directory(path: Path) -> None:
    flags = getattr(os, "O_DIRECTORY", 0)
    if os.name != "posix" or not flags:
        raise WorkflowError("durable state updates require POSIX directory fsync")
    try:
        descriptor = os.open(path, os.O_RDONLY | flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except (AttributeError, NotImplementedError, OSError) as exc:
        raise WorkflowError("durable state updates require POSIX directory fsync") from exc


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


def parse_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"{label} must contain one JSON object") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"{label} must contain one JSON object")
    return value


def read_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise WorkflowError(f"{label} must be a regular non-symlink file")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise WorkflowError(f"{label} must contain one JSON object") from exc
    return parse_object(raw, label)


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
        # The issue-links API returns the entire collection, including at CE's
        # 100-link boundary; a second page would repeat that same collection.
        if len(value) < 100 or re.fullmatch(
            r"projects/[^/]+/issues/[0-9]+/links", endpoint.split("?", maxsplit=1)[0]
        ):
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
    home = xdg_state_home()
    return private_directory(home / "agent-skills" / "task-triage" / digest(scope)[:32])


def load_analysis_index(root: Path) -> dict[str, Any]:
    path = root / "analysis-index.json"
    if not path.exists():
        return {"items": {}}
    value = read_object(path, "analysis index")
    if value.get("schema") != ANALYSIS_INDEX_SCHEMA or not isinstance(value.get("items"), dict):
        return {"items": {}}
    return value


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

    def numeric_id(note: dict[str, Any]) -> int | None:
        note_id = note.get("id")
        if type(note_id) is int:
            return note_id
        if isinstance(note_id, str) and note_id.isdecimal():
            return int(note_id)
        return None

    ordered = sorted(notes, key=lambda note: str(note.get("created_at") or ""))
    result: list[dict[str, Any]] = []
    start = 0
    while start < len(ordered):
        timestamp = str(ordered[start].get("created_at") or "")
        end = start + 1
        while end < len(ordered) and str(ordered[end].get("created_at") or "") == timestamp:
            end += 1
        group = ordered[start:end]
        if all(numeric_id(note) is not None for note in group):
            group.sort(key=lambda note: cast("int", numeric_id(note)))
        result.extend(group)
        start = end
    return result


def validate_message(snapshot: dict[str, Any], value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"target", "body"}:
        raise WorkflowError(f"{label} must contain target and body")
    target, _ = conversation_for(snapshot, value["target"], label)
    return {"target": target, "body": text(value["body"], f"{label} body")}


def validate_information_request(
    snapshot: dict[str, Any], current_user: dict[str, Any], value: object, label: str
) -> dict[str, Any]:
    expected = {
        "action",
        "target",
        "body",
        "prior_note_ids",
        "rationale",
        "standalone_reason",
    }
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
            or value["standalone_reason"] is not None
        ):
            raise WorkflowError(f"{label} with no action must not contain publication data")
        return {
            "action": action,
            "target": None,
            "body": None,
            "prior_note_ids": [],
            "rationale": rationale,
            "standalone_reason": None,
        }
    target, discussions = conversation_for(snapshot, value["target"], label)
    if target["kind"] == "issue":
        issue = snapshot.get("issue")
        if not isinstance(issue, dict) or issue.get("state") != "opened":
            raise WorkflowError(f"{label} target issue is not open")
    body = text(value["body"], f"{label} body")
    prior_note_ids = value["prior_note_ids"]
    required = {"new": 0, "ping_1": 1, "ping_2": 2, "close": 3, "close_fixed": 0}[action]
    if action not in {"new", "close_fixed"} and target["discussion_id"] is None:
        raise WorkflowError(f"{label} follow-up must target the observed discussion")
    standalone_reason = value["standalone_reason"]
    if action in {"new", "close_fixed"} and target["discussion_id"] is None:
        standalone_reason = text(standalone_reason, f"{label} standalone_reason")
    elif standalone_reason is not None:
        raise WorkflowError(f"{label} standalone_reason is valid only for a standalone new action")
    if (
        not isinstance(prior_note_ids, list)
        or len(prior_note_ids) != required
        or not all(positive(note_id) for note_id in prior_note_ids)
        or len(set(prior_note_ids)) != len(prior_note_ids)
    ):
        raise WorkflowError(f"{label} does not follow the information-request sequence")
    if action in {"close", "close_fixed"} and target["kind"] != "issue":
        raise WorkflowError(f"{label} may close only an issue")
    notes = discussion_notes(discussions, target["discussion_id"])
    if action == "new" and target["discussion_id"] is not None:
        latest = next((note for note in reversed(notes) if note.get("system") is not True), None)
        author = latest.get("author") if isinstance(latest, dict) else None
        if not isinstance(author, dict) or author.get("id") == current_user["id"]:
            raise WorkflowError(
                f"{label} new cycle in an existing discussion requires a latest participant reply"
            )
    if action == "close_fixed" and target["discussion_id"] is not None:
        # Closing a quietly fixed issue must not silently abandon the agent's
        # own unanswered question in the targeted discussion.
        latest = next((note for note in reversed(notes) if note.get("system") is not True), None)
        author = latest.get("author") if isinstance(latest, dict) else None
        if isinstance(author, dict) and author.get("id") == current_user["id"]:
            raise WorkflowError(
                f"{label} may not close an issue whose latest note is the current user's "
                "unanswered request; assess the reply first"
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
        "standalone_reason": standalone_reason,
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
            or set(link) != {"target_project_id", "target_issue_iid", "link_type"}
            or not positive(link.get("target_project_id"))
            or not positive(link.get("target_issue_iid"))
            or link.get("link_type") not in {"relates_to", "blocks", "is_blocked_by"}
        ):
            raise WorkflowError("proposed issue link is invalid")
    link_keys = {
        (link["target_project_id"], link["target_issue_iid"], link["link_type"]) for link in links
    }
    if len(link_keys) != len(links):
        raise WorkflowError("proposed issue links contain duplicates")
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


def text_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise WorkflowError(f"{label} must be a list")
    return [text(item, f"{label}[{index}]") for index, item in enumerate(value)]


def validate_agent_recommendation(value: object) -> dict[str, Any]:
    expected = {
        "proposal",
        "rationale",
        "assumptions",
        "confidence",
        "alternatives",
        "reconsider_if",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise WorkflowError("agent recommendation fields are invalid")
    confidence = value["confidence"]
    if confidence not in CONFIDENCE:
        raise WorkflowError("agent recommendation confidence is invalid")
    return {
        "proposal": text(value["proposal"], "agent recommendation proposal"),
        "rationale": text(value["rationale"], "agent recommendation rationale"),
        "assumptions": text_list(value["assumptions"], "agent recommendation assumptions"),
        "confidence": confidence,
        "alternatives": text_list(value["alternatives"], "agent recommendation alternatives"),
        "reconsider_if": text(value["reconsider_if"], "agent recommendation reconsider_if"),
    }


def observed_issue_targets(collection: dict[str, Any]) -> set[tuple[str, int, int]]:
    targets = {
        (
            item["target"]["hostname"],
            item["target"]["project_id"],
            item["target"]["iid"],
        )
        for item in collection["items"]
    }
    for key, context in collection["context"].items():
        if not isinstance(context, dict) or not isinstance(context.get("issues"), list):
            continue
        hostname = key.rsplit(":", 1)[0]
        try:
            project_id = int(key.rsplit(":", 1)[1])
        except (IndexError, ValueError):
            continue
        for issue in context["issues"]:
            if isinstance(issue, dict) and positive(issue.get("iid")):
                targets.add((hostname, project_id, issue["iid"]))
    for item in collection["items"]:
        hostname = item["target"]["hostname"]
        snapshot = read_object(Path(item["evidence_path"]), "issue evidence")
        for link in snapshot.get("links", []):
            if not isinstance(link, dict):
                continue
            for candidate in (link, link.get("source_issue"), link.get("target_issue")):
                if (
                    isinstance(candidate, dict)
                    and positive(candidate.get("project_id"))
                    and positive(candidate.get("iid"))
                ):
                    targets.add((hostname, candidate["project_id"], candidate["iid"]))
    return targets


def validate_observed_link_evidence(snapshot: dict[str, Any]) -> None:
    links = snapshot.get("links", [])
    if not isinstance(links, list):
        raise WorkflowError("observed issue links are invalid")
    for link in links:
        if (
            not isinstance(link, dict)
            or not positive(link.get("id"))
            or link.get("link_type") not in {"relates_to", "blocks", "is_blocked_by"}
        ):
            raise WorkflowError("observed issue link evidence is incomplete")
        candidates = [link, link.get("source_issue"), link.get("target_issue")]
        if not any(
            isinstance(candidate, dict)
            and positive(candidate.get("project_id"))
            and positive(candidate.get("iid"))
            for candidate in candidates
        ):
            raise WorkflowError("observed issue link identity is invalid")


def observed_issue_links(
    snapshot: dict[str, Any], project_id: int, iid: int
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for link in snapshot.get("links", []):
        if not isinstance(link, dict):
            continue
        candidates = [link, link.get("source_issue"), link.get("target_issue")]
        if any(
            isinstance(candidate, dict)
            and candidate.get("project_id") == project_id
            and candidate.get("iid") == iid
            for candidate in candidates
        ):
            relation_type = link.get("link_type")
            if relation_type not in {"relates_to", "blocks", "is_blocked_by"}:
                raise WorkflowError("observed issue link type is invalid")
            # REST list responses expose the relationship ID separately from the issue ID.
            link_id = link.get("issue_link_id", link.get("id"))
            if "issue_link_id" in link and not positive(link_id):
                raise WorkflowError("observed issue link has an invalid relationship ID")
            if not positive(link_id):
                matching = next(
                    (
                        candidate
                        for candidate in candidates
                        if isinstance(candidate, dict)
                        and candidate.get("project_id") == project_id
                        and candidate.get("iid") == iid
                    ),
                    None,
                )
                link_id = matching.get("id") if isinstance(matching, dict) else None
            if not positive(link_id):
                raise WorkflowError("observed issue link has no stable numeric ID")
            result.append({"id": link_id, "relation_type": relation_type})
    return result


def validate_issue_relations(
    value: object,
    *,
    snapshot: dict[str, Any],
    evidence_target: dict[str, Any],
    observed_targets: set[tuple[str, int, int]],
    proposed_changes: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise WorkflowError("issue relations must be a list")
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    links = proposed_changes.get("links", [])
    messages = proposed_changes.get("messages", [])
    for index, relation in enumerate(value):
        expected = {
            "target_hostname",
            "target_project_id",
            "target_issue_iid",
            "relation_type",
            "rationale",
            "existing_link",
            "comment",
        }
        if not isinstance(relation, dict) or set(relation) != expected:
            raise WorkflowError(f"issue_relations[{index}] fields are invalid")
        hostname = relation["target_hostname"]
        project_id = relation["target_project_id"]
        iid = relation["target_issue_iid"]
        if (
            not isinstance(hostname, str)
            or not hostname
            or hostname != evidence_target["hostname"]
            or not positive(project_id)
            or not positive(iid)
        ):
            raise WorkflowError(f"issue_relations[{index}] target is invalid")
        target = (hostname, project_id, iid)
        if (
            target not in observed_targets
            or target
            == (
                evidence_target["hostname"],
                evidence_target["project_id"],
                evidence_target["iid"],
            )
            or target in seen
        ):
            raise WorkflowError(f"issue_relations[{index}] target is invalid")
        seen.add(target)
        relation_type = relation["relation_type"]
        if relation_type not in {"relates_to", "blocks", "is_blocked_by"}:
            raise WorkflowError(f"issue_relations[{index}].relation_type is invalid")
        observed_links = observed_issue_links(snapshot, project_id, iid)
        if len(observed_links) > 1:
            raise WorkflowError("multiple observed links exist for one issue relation target")
        existing_link = relation["existing_link"]
        if existing_link is not None and (
            not isinstance(existing_link, dict)
            or set(existing_link) != {"id", "relation_type"}
            or not positive(existing_link.get("id"))
            or existing_link.get("relation_type") not in {"relates_to", "blocks", "is_blocked_by"}
        ):
            raise WorkflowError(f"issue_relations[{index}].existing_link is invalid")
        observed_link = observed_links[0] if observed_links else None
        if existing_link != observed_link:
            raise WorkflowError("issue relation existing_link does not match collected evidence")
        comment = relation["comment"]
        if comment is not None:
            comment = text(comment, f"issue_relations[{index}].comment")
            if not any(
                message["body"] == comment
                and message["target"]["kind"] == "issue"
                and message["target"]["project_id"] == evidence_target["project_id"]
                and message["target"]["iid"] == evidence_target["iid"]
                for message in messages
            ):
                raise WorkflowError("an issue relation comment requires a matching issue message")
        result.append(
            {
                "target_hostname": hostname,
                "target_project_id": project_id,
                "target_issue_iid": iid,
                "relation_type": relation_type,
                "rationale": text(relation["rationale"], f"issue_relations[{index}].rationale"),
                "existing_link": existing_link,
                "comment": comment,
            }
        )
    expected_links = {
        (
            relation["target_project_id"],
            relation["target_issue_iid"],
            relation["relation_type"],
        )
        for relation in result
        if relation["existing_link"] is None
        or relation["existing_link"]["relation_type"] != relation["relation_type"]
    }
    proposed_links = {
        (link["target_project_id"], link["target_issue_iid"], link["link_type"]) for link in links
    }
    if proposed_links != expected_links:
        raise WorkflowError("proposed issue links must exactly match missing issue relations")
    return result


def observed_participants(snapshot: dict[str, Any]) -> set[str]:
    usernames: set[str] = set()
    issue = snapshot.get("issue")
    if isinstance(issue, dict):
        assignees = issue.get("assignees")
        people = [issue.get("author"), *(assignees if isinstance(assignees, list) else [])]
        for person in people:
            if isinstance(person, dict) and isinstance(person.get("username"), str):
                usernames.add(person["username"])
    for merge_request in [*snapshot.get("merge_requests", []), *snapshot.get("closed_by", [])]:
        if not isinstance(merge_request, dict):
            continue
        author = merge_request.get("author")
        if isinstance(author, dict) and isinstance(author.get("username"), str):
            usernames.add(author["username"])
    conversations = [snapshot.get("discussions", [])]
    conversations.extend(
        item.get("discussions", [])
        for item in snapshot.get("merge_request_conversations", [])
        if isinstance(item, dict)
    )
    for discussions in conversations:
        if not isinstance(discussions, list):
            continue
        for note in discussion_notes(discussions, None):
            author = note.get("author")
            if isinstance(author, dict) and isinstance(author.get("username"), str):
                usernames.add(author["username"])
    return usernames


def validate_questions(
    collection: dict[str, Any], value: object, items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise WorkflowError("analysis questions must be a list")
    evidence = {item["evidence_digest"]: item for item in collection["items"]}
    result: list[dict[str, Any]] = []
    for index, question in enumerate(value):
        expected = {
            "evidence_digest",
            "kind",
            "tldr",
            "evidence",
            "decision",
            "why_now",
            "planning_effect",
            "recommendation",
            "options",
            "fallback",
        }
        if not isinstance(question, dict) or set(question) != expected:
            raise WorkflowError(f"questions[{index}] fields are invalid")
        evidence_digest = text(question["evidence_digest"], f"questions[{index}].evidence_digest")
        if evidence_digest not in evidence:
            raise WorkflowError(f"questions[{index}] evidence binding is invalid")
        kind = question["kind"]
        if kind not in {"authority", "private_context", "bounded_technical"}:
            raise WorkflowError(f"questions[{index}] kind is invalid")
        options = question["options"]
        if not isinstance(options, list) or not 2 <= len(options) <= 5:
            raise WorkflowError(f"questions[{index}] options are invalid")
        if kind == "bounded_technical" and len(options) > 3:
            raise WorkflowError("bounded technical questions require two or three options")
        normalized_options = []
        option_labels: set[str] = set()
        for option_index, option in enumerate(options):
            if not isinstance(option, dict) or set(option) != {"label", "description"}:
                raise WorkflowError(f"questions[{index}].options[{option_index}] is invalid")
            label = text(option["label"], f"questions[{index}].options[{option_index}].label")
            if label in option_labels:
                raise WorkflowError(f"questions[{index}] option labels must be unique")
            option_labels.add(label)
            normalized_options.append(
                {
                    "label": label,
                    "description": text(
                        option["description"],
                        f"questions[{index}].options[{option_index}].description",
                    ),
                }
            )
        recommendation = question["recommendation"]
        if not isinstance(recommendation, dict) or set(recommendation) != {
            "option",
            "rationale",
        }:
            raise WorkflowError(f"questions[{index}] recommendation is invalid")
        recommended_option = text(
            recommendation["option"], f"questions[{index}].recommendation.option"
        )
        if recommended_option not in option_labels:
            raise WorkflowError(f"questions[{index}] recommended option was not offered")
        evidence_item = evidence[evidence_digest]
        snapshot = read_object(Path(evidence_item["evidence_path"]), "issue evidence")
        target = evidence_item["target"]
        context = collection["context"].get(f"{target['hostname']}:{target['project_id']}")
        current_user = context.get("current_user") if isinstance(context, dict) else None
        if not isinstance(current_user, dict):
            raise WorkflowError("authenticated GitLab user evidence is unavailable")
        fallback = question["fallback"]
        participants = observed_participants(snapshot)
        normalized_fallback = None
        if fallback is not None:
            if not isinstance(fallback, dict) or set(fallback) != {"participant", "target", "body"}:
                raise WorkflowError(f"questions[{index}] fallback fields are invalid")
            participant = fallback["participant"]
            if (
                not isinstance(participant, str)
                or participant not in participants
                or participant == current_user["username"]
            ):
                raise WorkflowError(f"questions[{index}] fallback participant is invalid")
            fallback_target, _ = conversation_for(
                snapshot, fallback["target"], f"questions[{index}] fallback"
            )
            fallback_body = text(fallback["body"], f"questions[{index}] fallback body")
            item = next(
                candidate
                for candidate in items
                if candidate["evidence"]["evidence_digest"] == evidence_digest
            )
            if not any(
                request["action"] != "none"
                and request["target"] == fallback_target
                and request["body"] == fallback_body
                for request in item["information_requests"]
            ):
                raise WorkflowError(
                    f"questions[{index}] fallback must match an information request"
                )
            normalized_fallback = {
                "participant": participant,
                "target": fallback_target,
                "body": fallback_body,
            }
        result.append(
            {
                "evidence_digest": evidence_digest,
                "kind": kind,
                "tldr": text(question["tldr"], f"questions[{index}].tldr"),
                "evidence": text(question["evidence"], f"questions[{index}].evidence"),
                "decision": text(question["decision"], f"questions[{index}].decision"),
                "why_now": text(question["why_now"], f"questions[{index}].why_now"),
                "planning_effect": text(
                    question["planning_effect"], f"questions[{index}].planning_effect"
                ),
                "recommendation": {
                    "option": recommended_option,
                    "rationale": text(
                        recommendation["rationale"],
                        f"questions[{index}].recommendation.rationale",
                    ),
                },
                "options": normalized_options,
                "fallback": normalized_fallback,
            }
        )
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
    observed_targets = observed_issue_targets(collection)
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
        validate_observed_link_evidence(snapshot)
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
        agent_recommendation = validate_agent_recommendation(raw.get("agent_recommendation"))
        if "related_issues" in raw or "partial_relations" in raw:
            raise WorkflowError("legacy issue relation fields are not supported")
        if "issue_relations" not in raw:
            raise WorkflowError("analysis issue_relations field is required")
        issue_relations = validate_issue_relations(
            raw["issue_relations"],
            snapshot=snapshot,
            evidence_target=target,
            observed_targets=observed_targets,
            proposed_changes=proposed_changes,
        )
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
                "agent_recommendation": agent_recommendation,
                "issue_relations": issue_relations,
                "proposed_changes": proposed_changes,
                "information_requests": information_requests,
                "evidence": evidence_item,
            }
        )
    return result


def validate_execution_plan(
    top_value: object, parallel_value: object, items: list[dict[str, Any]]
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    accepted = {
        item["evidence"]["evidence_digest"]
        for item in items
        if item["release_plan"]["decision"]["status"] == "accepted"
    }
    if not isinstance(top_value, list) or len(top_value) > 5:
        raise WorkflowError("top_five must contain at most five items")
    top: list[dict[str, str]] = []
    top_seen: set[str] = set()
    for index, value in enumerate(top_value):
        if not isinstance(value, dict) or set(value) != {"evidence_digest", "rationale"}:
            raise WorkflowError(f"top_five[{index}] fields are invalid")
        evidence_digest = text(value["evidence_digest"], f"top_five[{index}].evidence_digest")
        if evidence_digest not in accepted or evidence_digest in top_seen:
            raise WorkflowError(f"top_five[{index}] must bind a unique accepted item")
        top_seen.add(evidence_digest)
        top.append(
            {
                "evidence_digest": evidence_digest,
                "rationale": text(value["rationale"], f"top_five[{index}].rationale"),
            }
        )
    if not isinstance(parallel_value, list):
        raise WorkflowError("parallel_groups must be a list")
    groups: list[dict[str, Any]] = []
    grouped: set[str] = set()
    for index, value in enumerate(parallel_value):
        if not isinstance(value, dict) or set(value) != {"evidence_digests", "rationale"}:
            raise WorkflowError(f"parallel_groups[{index}] fields are invalid")
        evidence_digests = value["evidence_digests"]
        if not isinstance(evidence_digests, list) or not evidence_digests:
            raise WorkflowError(f"parallel_groups[{index}].evidence_digests must be non-empty")
        normalized = [
            text(digest_value, f"parallel_groups[{index}].evidence_digests[{item_index}]")
            for item_index, digest_value in enumerate(evidence_digests)
        ]
        if (
            len(set(normalized)) != len(normalized)
            or any(digest_value not in accepted for digest_value in normalized)
            or any(digest_value in grouped for digest_value in normalized)
        ):
            raise WorkflowError(f"parallel_groups[{index}] must bind unique accepted items")
        grouped.update(normalized)
        groups.append(
            {
                "evidence_digests": normalized,
                "rationale": text(value["rationale"], f"parallel_groups[{index}].rationale"),
            }
        )
    return top, groups


def markdown_list(value: object, locale: str) -> str:
    if not isinstance(value, list) or not value:
        return f"- {TEXT[locale]['none']}"
    return "\n".join(f"- {item}" for item in value)


def display(value: object, locale: str, field: str) -> str:
    translations = RU_VALUES.get(field, {})
    if locale == "ru" and (value is None or isinstance(value, str)) and value in translations:
        return translations[value]
    return str(value)


def recommendation_markdown(value: dict[str, Any], locale: str) -> list[str]:
    labels = TEXT[locale]
    return [
        f"- {labels['proposal']}: {value['proposal']}",
        f"- {labels['rationale']}: {value['rationale']}",
        f"- {labels['assumptions']}: "
        + ("; ".join(value["assumptions"]) if value["assumptions"] else labels["none"]),
        f"- {labels['confidence']}: {value['confidence']}",
        f"- {labels['alternatives']}: "
        + ("; ".join(value["alternatives"]) if value["alternatives"] else labels["none"]),
        f"- {labels['reconsider_if']}: {value['reconsider_if']}",
    ]


def issue_relations_markdown(value: list[dict[str, Any]], locale: str) -> str:
    if not value:
        return f"- {TEXT[locale]['none']}"
    return "\n".join(
        f"- {relation['target_hostname']}:{relation['target_project_id']}"
        f"#{relation['target_issue_iid']} [{relation['relation_type']}; "
        f"{TEXT[locale]['relation_existing'] if relation['existing_link'] and relation['existing_link']['relation_type'] == relation['relation_type'] else TEXT[locale]['relation_proposed']}]: "
        f"{relation['rationale']}"
        for relation in value
    )


def code_block(content: str, language: str) -> list[str]:
    fence = "`" * max(3, max((len(match) + 1 for match in re.findall(r"`+", content)), default=3))
    return [f"{fence}{language}", content, fence]


def shell_quote(value: str) -> str:
    return shlex.quote(value)


def oneline(value: object) -> str:
    """Collapse one analysis rationale into a single comment line."""
    return " ".join(str(value).split())


def inline_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def stream_digest(value: str) -> str:
    """Digest the exact byte stream that `jq -r ... | sha256sum` hashes."""
    return hashlib.sha256(value.encode()).hexdigest()


def bodies_digest(bodies: list[str]) -> str:
    """Replicate `jq -sr '[..] | sort | .[]' | sha256sum` for snapshot note bodies."""
    return stream_digest("".join(f"{body}\n" for body in sorted(bodies)))


def field_digest(value: object) -> str:
    """Replicate `jq -r '. // \"\"' | sha256sum` for one observed text field."""
    return stream_digest(f"{value or ''}\n")


def observed_updated_at(snapshot: dict[str, Any], target: dict[str, Any]) -> str | None:
    """Return the snapshot updated_at timestamp for an observed write target."""
    if target.get("kind", "issue") == "issue":
        value = snapshot.get("issue", {}).get("updated_at")
    else:
        value = next(
            (
                item.get("updated_at")
                for item in [*snapshot.get("merge_requests", []), *snapshot.get("closed_by", [])]
                if isinstance(item, dict)
                and item.get("project_id") == target.get("project_id")
                and item.get("iid") == target.get("iid")
            ),
            None,
        )
    return value if isinstance(value, str) and value.strip() else None


def conversation_bodies(discussions: list[dict[str, Any]], discussion_id: str | None) -> list[str]:
    """Non-system note bodies of one conversation, or of every discussion."""
    return [
        str(note.get("body") or "")
        for note in discussion_notes(discussions, discussion_id)
        if note.get("system") is not True
    ]


def link_match_expression() -> str:
    return (
        "((.project_id == $p and .iid == $i)"
        " or (.source_issue.project_id == $p and .source_issue.iid == $i)"
        " or (.target_issue.project_id == $p and .target_issue.iid == $i))"
    )


def guard_stop(key: str, locale: str) -> str:
    return f"{{ echo {shell_quote(TEXT[locale][key])} >&2; false; }}"


def user_guard(host: str, current_user: dict[str, Any], locale: str) -> str:
    """Stop the block before any write when the authenticated user changed."""
    check = (
        f"(glab api --hostname {shell_quote(host)} user"
        f" | jq -e --argjson id {int(current_user['id'])}"
        f" --arg username {shell_quote(str(current_user['username']))}"
        " '.id == $id and .username == $username' >/dev/null"
        f" || {guard_stop('guard_user_stop', locale)}) &&"
    )
    return "\n".join([f"# {TEXT[locale]['guard_user']}", check])


def fresh_guard(host: str, endpoint: str, updated_at: str, locale: str) -> str:
    """Stop the block when the target changed after triage."""
    check = (
        f'([ "$(glab api --hostname {shell_quote(host)} {shell_quote(endpoint)}'
        f" | jq -r '.updated_at')\" = {shell_quote(updated_at)} ]"
        f" || {guard_stop('guard_fresh_stop', locale)}) &&"
    )
    return "\n".join([f"# {TEXT[locale]['guard_fresh']}", check])


def open_guard(host: str, endpoint: str, locale: str) -> str:
    """Stop the block when the target issue or merge request is closed."""
    check = (
        f"(glab api --hostname {shell_quote(host)} {shell_quote(endpoint)}"
        " | jq -e '.state == \"opened\"' >/dev/null"
        f" || {guard_stop('guard_open_stop', locale)}) &&"
    )
    return "\n".join([f"# {TEXT[locale]['guard_open']}", check])


def title_guard(host: str, endpoint: str, observed_title: str, locale: str) -> str:
    check = (
        f'([ "$(glab api --hostname {shell_quote(host)} {shell_quote(endpoint)}'
        f" | jq -r '.title')\" = {shell_quote(observed_title)} ]"
        f" || {guard_stop('guard_title_stop', locale)}) &&"
    )
    return "\n".join([f"# {TEXT[locale]['guard_title']}", check])


def description_guard(host: str, endpoint: str, value: object, locale: str) -> str:
    check = (
        f'(body_digest="$(glab api --hostname {shell_quote(host)} {shell_quote(endpoint)}'
        ' | jq -r \'.description // ""\' | sha256sum)"'
        f' && [ "${{body_digest%% *}}" = {shell_quote(field_digest(value))} ]'
        f" || {guard_stop('guard_description_stop', locale)}) &&"
    )
    return "\n".join([f"# {TEXT[locale]['guard_description']}", check])


def labels_guard(host: str, endpoint: str, expected: list[str], locale: str) -> str:
    check = (
        f'([ "$(glab api --hostname {shell_quote(host)} {shell_quote(endpoint)}'
        ' | jq -c \'[(.labels // [])[] | if type == "object" then .name else . end]'
        " | sort')\" = "
        f"{shell_quote(inline_json(sorted(expected)))} ]"
        f" || {guard_stop('guard_labels_stop', locale)}) &&"
    )
    return "\n".join([f"# {TEXT[locale]['guard_labels']}", check])


def milestone_guard(host: str, endpoint: str, milestone_id: int | None, locale: str) -> str:
    expression = (
        ".milestone == null" if milestone_id is None else f".milestone.id == {int(milestone_id)}"
    )
    check = (
        f"(glab api --hostname {shell_quote(host)} {shell_quote(endpoint)}"
        f" | jq -e '{expression}' >/dev/null"
        f" || {guard_stop('guard_milestone_stop', locale)}) &&"
    )
    return "\n".join([f"# {TEXT[locale]['guard_milestone']}", check])


def conversation_guard(
    host: str,
    discussions_endpoint: str,
    discussion_id: str | None,
    expected: str,
    locale: str,
) -> str:
    """Stop the block when the conversation changed or the message is published."""
    selector = (
        "[.[][] | .notes[]? | select(.system != true) | .body]"
        if discussion_id is None
        else "[.[][] | select(.id == $d) | .notes[]? | select(.system != true) | .body]"
    )
    arguments = "" if discussion_id is None else f" --arg d {shell_quote(discussion_id)}"
    check = (
        f'(note_digest="$(glab api --hostname {shell_quote(host)}'
        f" --paginate {shell_quote(discussions_endpoint + '?per_page=100')}"
        f" | jq -sr{arguments} '{selector} | sort | .[]'"
        ' | sha256sum)"'
        f' && [ "${{note_digest%% *}}" = {shell_quote(expected)} ]'
        f" || {guard_stop('guard_conversation_stop', locale)}) &&"
    )
    return "\n".join([f"# {TEXT[locale]['guard_conversation']}", check])


def absent_link_guard(
    host: str, links_endpoint: str, project_id: int, iid: int, locale: str
) -> str:
    check = (
        f'([ "$(glab api --hostname {shell_quote(host)} '
        f"{shell_quote(links_endpoint + '?per_page=100')}"
        f" | jq --argjson p {int(project_id)} --argjson i {int(iid)}"
        f" '[.[] | select({link_match_expression()})] | length')\" = 0 ]"
        f" || {guard_stop('guard_links_stop', locale)}) &&"
    )
    return "\n".join([f"# {TEXT[locale]['guard_links']}", check])


def open_mr_guard(host: str, project_id: int, iid: int, locale: str) -> str:
    """Stop the block when an open merge request already references the issue.

    One glab search over open merge requests by the issue reference; a match,
    a non-list answer, or a failed read stops the block before any write.
    """
    search = urllib.parse.quote(f"#{int(iid)}", safe="")
    endpoint = f"projects/{int(project_id)}/merge_requests?state=opened&search={search}"
    check = (
        f"(glab api --hostname {shell_quote(host)} {shell_quote(endpoint)}"
        " | jq -e 'type == \"array\" and length == 0' >/dev/null"
        f" || {guard_stop('guard_open_mr_stop', locale)}) &&"
    )
    return "\n".join([f"# {TEXT[locale]['guard_open_mr']}", check])


def inline_write(
    host: str,
    method: str,
    endpoint: str,
    body: str,
    *,
    chain: bool = True,
    expand: bool = False,
    suffix: str = "",
) -> str:
    """Render one direct glab api write with an inline JSON heredoc body."""
    delimiter = "TRIAGE_JSON_" + hashlib.sha256(body.encode()).hexdigest()[:16].upper()
    boundary = delimiter if expand else f"'{delimiter}'"
    command = (
        f"glab api --hostname {shell_quote(host)} --method {method} {shell_quote(endpoint)}"
        f" --header 'Content-Type: application/json' --input - <<{boundary}{suffix}"
    )
    if chain:
        command += " &&"
    return f"{command}\n{body}\n{delimiter}"


def unchain(command: str) -> str:
    """Drop the trailing continuation operator from the block's final write."""
    head, *rest = command.split("\n")
    return "\n".join([head.removesuffix(" &&"), *rest])


def commands_for(
    item: dict[str, Any], current_user: dict[str, Any], locale: str
) -> list[dict[str, Any]]:
    """Build one guarded, fail-fast direct-command block per triage action.

    The first emitted writing block of the task verifies the snapshot
    updated_at; every later block verifies its own semantic preconditions
    against a fresh read. A stage whose precondition cannot be precomputed is
    emitted as a regeneration instruction instead of a command.
    """
    target = item["evidence"]["target"]
    host = target["hostname"]
    issue_endpoint = f"projects/{target['project_id']}/issues/{target['iid']}"
    snapshot = read_object(Path(item["evidence"]["evidence_path"]), "issue evidence")
    issue = snapshot.get("issue", {})
    proposed = item["proposed_changes"]
    actions: list[dict[str, Any]] = []

    def endpoints(conversation_target: dict[str, Any]) -> tuple[str, str]:
        collection = "issues" if conversation_target["kind"] == "issue" else "merge_requests"
        base = f"projects/{conversation_target['project_id']}/{collection}/{conversation_target['iid']}"
        return base, f"{base}/discussions"

    def note_endpoint(conversation_target: dict[str, Any]) -> str:
        base, _ = endpoints(conversation_target)
        if conversation_target["discussion_id"] is None:
            return f"{base}/notes"
        encoded = urllib.parse.quote(conversation_target["discussion_id"], safe="")
        return f"{base}/discussions/{encoded}/notes"

    def notes_preconditions(
        conversation_target: dict[str, Any], discussions: list[dict[str, Any]]
    ) -> list[str]:
        base, discussions_endpoint = endpoints(conversation_target)
        discussion_id = conversation_target["discussion_id"]
        return [
            open_guard(host, base, locale),
            conversation_guard(
                host,
                discussions_endpoint,
                discussion_id,
                bodies_digest(conversation_bodies(discussions, discussion_id)),
                locale,
            ),
        ]

    for field, kind in (("title", "title"), ("description", "description"), ("labels", "labels")):
        if field not in proposed:
            continue
        value = proposed[field]
        payload_value = ",".join(value) if field == "labels" else value
        if field == "title":
            semantic = [title_guard(host, issue_endpoint, str(issue.get("title") or ""), locale)]
        elif field == "description":
            semantic = [description_guard(host, issue_endpoint, issue.get("description"), locale)]
        else:
            semantic = [
                labels_guard(
                    host,
                    issue_endpoint,
                    [str(label) for label in (issue.get("labels") or [])],
                    locale,
                )
            ]
        actions.append(
            {
                "kind": kind,
                "fresh_target": target,
                "fresh_endpoint": issue_endpoint,
                "semantic": semantic,
                "segments": [
                    (
                        TEXT[locale][f"action_{kind}"],
                        inline_write(
                            host, "PUT", issue_endpoint, inline_json({field: payload_value})
                        ),
                    )
                ],
                "preview": json.dumps({field: value}, ensure_ascii=False, indent=2),
            }
        )

    release_plan = item["release_plan"]
    decision = release_plan["decision"]["status"]
    milestone = release_plan["milestone"]
    current = issue.get("milestone")
    current_id = current.get("id") if isinstance(current, dict) else None
    expected_milestone = current_id if isinstance(current_id, int) else None
    if decision == "accepted" and milestone["status"] == "selected":
        actions.append(
            {
                "kind": "milestone",
                "fresh_target": target,
                "fresh_endpoint": issue_endpoint,
                "semantic": [
                    open_mr_guard(host, target["project_id"], target["iid"], locale),
                    milestone_guard(host, issue_endpoint, expected_milestone, locale),
                ],
                "segments": [
                    (
                        TEXT[locale]["action_milestone"],
                        inline_write(
                            host,
                            "PUT",
                            issue_endpoint,
                            inline_json({"milestone_id": milestone["candidate"]["id"]}),
                        ),
                    )
                ],
                "preview": str(milestone["candidate"]["title"]),
            }
        )
    elif decision != "accepted" and milestone["status"] == "remove":
        actions.append(
            {
                "kind": "milestone",
                "fresh_target": target,
                "fresh_endpoint": issue_endpoint,
                "semantic": [
                    open_mr_guard(host, target["project_id"], target["iid"], locale),
                    milestone_guard(host, issue_endpoint, expected_milestone, locale),
                ],
                "segments": [
                    (
                        TEXT[locale]["action_milestone"],
                        inline_write(host, "PUT", issue_endpoint, inline_json({"milestone_id": 0})),
                    )
                ],
                "preview": json.dumps({"milestone_id": 0}, indent=2),
            }
        )
    elif decision == "accepted" and milestone["status"] == "create":
        title = milestone["candidate"]["title"]
        milestones_endpoint = (
            f"projects/{target['project_id']}"
            "/milestones?include_parent_milestones=true&state=active&per_page=100"
        )
        create_block = "\n".join(
            [
                f"# {TEXT[locale]['guard_milestone_search']}",
                (
                    f"milestone_id=$(glab api --hostname {shell_quote(host)} "
                    f"{shell_quote(milestones_endpoint)}"
                    f" | jq -r --arg title {shell_quote(title)}"
                    " 'map(select(.title == $title) | .id) | first // empty' || true) &&"
                ),
                'if [ -z "$milestone_id" ]; then',
                "# " + TEXT[locale]["action_create_milestone"],
                (
                    "milestone_id=$("
                    + inline_write(
                        host,
                        "POST",
                        f"projects/{target['project_id']}/milestones",
                        inline_json({"title": title}),
                        chain=False,
                        suffix=" | jq -er '.id | numbers'",
                    )
                    + "\n)"
                ),
                "fi &&",
                f"# {TEXT[locale]['action_milestone']}",
                inline_write(
                    host,
                    "PUT",
                    issue_endpoint,
                    '{"milestone_id": $milestone_id}',
                    chain=False,
                    expand=True,
                ),
            ]
        )
        actions.append(
            {
                "kind": "create_milestone",
                "fresh_target": target,
                "fresh_endpoint": issue_endpoint,
                "semantic": [
                    open_mr_guard(host, target["project_id"], target["iid"], locale),
                    milestone_guard(host, issue_endpoint, expected_milestone, locale),
                ],
                "segments": [("", create_block)],
                "preview": json.dumps(
                    {"create": {"title": title}, "attach": {"milestone_id": "$milestone_id"}},
                    ensure_ascii=False,
                    indent=2,
                ),
            }
        )

    relation_by_link = {
        (
            relation["target_project_id"],
            relation["target_issue_iid"],
            relation["relation_type"],
        ): relation
        for relation in item["issue_relations"]
    }
    for link in proposed.get("links", []):
        relation = relation_by_link[
            (link["target_project_id"], link["target_issue_iid"], link["link_type"])
        ]
        existing_link = relation["existing_link"]
        links_endpoint = f"{issue_endpoint}/links"
        if existing_link is not None and existing_link["relation_type"] != link["link_type"]:
            match = f"{link_match_expression()} and .link_type == $t"
            arguments = (
                f"--argjson p {int(link['target_project_id'])}"
                f" --argjson i {int(link['target_issue_iid'])}"
                f" --arg t {shell_quote(existing_link['relation_type'])}"
            )
            stop = guard_stop("guard_links_stop", locale)
            create_block = "\n".join(
                [
                    f"# {TEXT[locale]['guard_links']}",
                    (
                        f"links=$(glab api --hostname {shell_quote(host)} "
                        f"{shell_quote(links_endpoint + '?per_page=100')}) &&"
                    ),
                    (
                        '([ "$(printf \'%s\' "$links" | jq '
                        f"{arguments} '[.[] | select({match})] | length')\" = 1 ] || {stop}) &&"
                    ),
                    (
                        "link_id=$(printf '%s' \"$links\" | jq -er "
                        f"{arguments} '.[] | select({match}) | .issue_link_id // .id') &&"
                    ),
                    (f'([ "$link_id" = {shell_quote(str(existing_link["id"]))} ] || {stop}) &&'),
                    f"# {TEXT[locale]['action_replace_link_delete']}",
                    (
                        "glab api --hostname "
                        f"{shell_quote(host)} --method DELETE "
                        f"{shell_quote(f'{links_endpoint}/{existing_link["id"]}')} &&"
                    ),
                    f"# {TEXT[locale]['action_replace_link_create']}",
                    inline_write(host, "POST", links_endpoint, inline_json(link), chain=False),
                ]
            )
            actions.append(
                {
                    "kind": "replace_link",
                    "fresh_target": target,
                    "fresh_endpoint": issue_endpoint,
                    "semantic": [],
                    "segments": [("", create_block)],
                    "preview": json.dumps(
                        {"delete": existing_link, "create": link},
                        ensure_ascii=False,
                        indent=2,
                    ),
                }
            )
            continue
        actions.append(
            {
                "kind": "link",
                "fresh_target": target,
                "fresh_endpoint": issue_endpoint,
                "semantic": [
                    absent_link_guard(
                        host,
                        links_endpoint,
                        link["target_project_id"],
                        link["target_issue_iid"],
                        locale,
                    )
                ],
                "segments": [
                    (
                        TEXT[locale]["action_link"],
                        inline_write(host, "POST", links_endpoint, inline_json(link)),
                    )
                ],
                "preview": json.dumps(link, ensure_ascii=False, indent=2),
            }
        )

    for message in proposed.get("messages", []):
        message_target, discussions = conversation_for(
            snapshot, message["target"], "proposed messages"
        )
        base, _ = endpoints(message_target)
        actions.append(
            {
                "kind": "message",
                "fresh_target": message_target,
                "fresh_endpoint": base,
                "semantic": notes_preconditions(message_target, discussions),
                "segments": [
                    (
                        TEXT[locale]["action_message"],
                        inline_write(
                            host,
                            "POST",
                            note_endpoint(message_target),
                            inline_json({"body": message["body"]}),
                        ),
                    )
                ],
                "preview": message["body"],
            }
        )

    for request in item["information_requests"]:
        if request["action"] == "none":
            continue
        request_target, discussions = conversation_for(
            snapshot, request["target"], "information request"
        )
        base, _ = endpoints(request_target)
        segments = [
            (
                TEXT[locale][f"action_information_{request['action']}"],
                inline_write(
                    host,
                    "POST",
                    note_endpoint(request_target),
                    inline_json({"body": request["body"]}),
                ),
            )
        ]
        if request["action"] in {"close", "close_fixed"}:
            segments.append(
                (
                    TEXT[locale]["action_close"],
                    inline_write(
                        host,
                        "PUT",
                        base,
                        inline_json({"state_event": "close"}),
                        chain=False,
                    ),
                )
            )
            preview = f"{request['body']}\n\n{json.dumps({'state_event': 'close'}, indent=2)}"
        else:
            preview = request["body"]
        semantic = notes_preconditions(request_target, discussions)
        if request["action"] in {"close", "close_fixed"}:
            semantic.insert(
                0, open_mr_guard(host, request_target["project_id"], request_target["iid"], locale)
            )
        actions.append(
            {
                "kind": f"information_{request['action']}",
                "fresh_target": request_target,
                "fresh_endpoint": base,
                "semantic": semantic,
                "segments": segments,
                "preview": preview,
            }
        )

    if item["actuality"]["status"] in {"obsolete", "duplicate"} and issue.get("state") == "opened":
        # An explicit information-request closure (stale or quietly fixed)
        # already publishes an explanation and closes the issue; the bare
        # close must not duplicate it.
        requested = any(
            request["action"] in {"close", "close_fixed"}
            and request["target"]["kind"] == "issue"
            and request["target"]["project_id"] == target["project_id"]
            and request["target"]["iid"] == target["iid"]
            for request in item["information_requests"]
        )
        if not requested:
            actions.append(
                {
                    "kind": "close",
                    "fresh_target": target,
                    "fresh_endpoint": issue_endpoint,
                    "semantic": [
                        open_mr_guard(host, target["project_id"], target["iid"], locale),
                        open_guard(host, issue_endpoint, locale),
                    ],
                    "segments": [
                        (
                            (
                                f"{TEXT[locale]['action_close']}: "
                                f"{oneline(item['actuality']['rationale'])}"
                            ),
                            inline_write(
                                host,
                                "PUT",
                                issue_endpoint,
                                inline_json({"state_event": "close"}),
                                chain=False,
                            ),
                        )
                    ],
                    "preview": json.dumps({"state_event": "close"}, indent=2),
                }
            )

    result: list[dict[str, Any]] = []
    fresh_pending = True
    for one in actions:
        lines = [user_guard(host, current_user, locale)]
        if fresh_pending:
            updated_at = observed_updated_at(snapshot, one["fresh_target"])
            if updated_at is None:
                result.append(
                    {
                        "kind": one["kind"],
                        "instruction": TEXT[locale]["guard_fresh_stop"],
                    }
                )
                continue
            lines.append(fresh_guard(host, one["fresh_endpoint"], updated_at, locale))
            fresh_pending = False
        else:
            lines.extend(one["semantic"])
        for position, (comment, command) in enumerate(one["segments"]):
            if comment:
                lines.append(f"# {comment}")
            if position == len(one["segments"]) - 1:
                # The final write must not dangle a continuation operator.
                lines.append(unchain(command))
            else:
                lines.append(command)
        result.append(
            {
                "kind": one["kind"],
                "preview": one["preview"],
                "command": "\n".join(lines),
            }
        )
    return result


def item_markdown(
    item: dict[str, Any], commands: list[dict[str, str]], locale: str, source_url: str
) -> str:
    evidence = item["evidence"]
    issue = read_object(Path(evidence["evidence_path"]), "issue evidence")["issue"]
    actuality, quality = item["actuality"], item["quality"]
    release_plan = item["release_plan"]
    semver = release_plan["semver"]
    labels = TEXT[locale]
    sections = [
        f"# {markdown_link_label(str(issue.get('title') or source_url))}",
        "",
        f"- {labels['source']}: {source_url}",
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
        f"## {labels['duplicates']}",
        "",
        markdown_list(item.get("duplicates"), locale),
        "",
        f"## {labels['issue_relations']}",
        "",
        issue_relations_markdown(item["issue_relations"], locale),
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
        f"## {labels['recommendation']}",
        "",
        *recommendation_markdown(item["agent_recommendation"], locale),
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
            sections.extend([f"### {labels['action_' + command['kind']]}", ""])
            if "instruction" in command:
                sections.extend([f"- {labels['regenerate']}: {command['instruction']}", ""])
                continue
            sections.extend(
                [
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


def summary_reference_maps(
    collection: dict[str, Any], items: list[dict[str, Any]]
) -> dict[str, dict[int, str]]:
    candidates: dict[str, dict[int, set[str]]] = {"#": {}, "!": {}}
    unresolved = "<unresolved>"

    def add(kind: str, iid: object, url: object) -> None:
        if positive(iid):
            candidate = url if isinstance(url, str) and url else unresolved
            candidates[kind].setdefault(iid, set()).add(candidate)

    for evidence in collection["items"]:
        target = evidence["target"]
        context = collection["context"].get(f"{target['hostname']}:{target['project_id']}")
        project_path = context.get("project_path") if isinstance(context, dict) else None
        add(
            "#",
            target["iid"],
            canonical_project_item_url(target["hostname"], project_path, "issues", target["iid"]),
        )
    for key, context in collection["context"].items():
        if not isinstance(context, dict):
            continue
        host = key.rsplit(":", 1)[0]
        project_path = context.get("project_path")
        for issue in context.get("issues", []):
            if not isinstance(issue, dict):
                continue
            add(
                "#",
                issue.get("iid"),
                canonical_project_item_url(host, project_path, "issues", issue.get("iid")),
            )
    for item in items:
        target = item["evidence"]["target"]
        host = target["hostname"]
        snapshot = read_object(Path(item["evidence"]["evidence_path"]), "issue evidence")
        for link in snapshot.get("links", []):
            if not isinstance(link, dict):
                continue
            for candidate in (link, link.get("source_issue"), link.get("target_issue")):
                if not isinstance(candidate, dict) or (
                    candidate.get("project_id") == target["project_id"]
                    and candidate.get("iid") == target["iid"]
                ):
                    continue
                add("#", candidate.get("iid"), canonical_linked_issue_url(host, candidate))
        for merge_request in [
            *snapshot.get("merge_requests", []),
            *snapshot.get("closed_by", []),
        ]:
            if isinstance(merge_request, dict):
                add("!", merge_request.get("iid"), canonical_merge_request_url(host, merge_request))
    return {
        kind: {
            iid: next(iter(urls))
            for iid, urls in values.items()
            if len(urls) == 1 and unresolved not in urls
        }
        for kind, values in candidates.items()
    }


def canonical_project_item_url(
    host: object, project_path: object, collection: str, iid: object
) -> str | None:
    if (
        not isinstance(host, str)
        or not host
        or not isinstance(project_path, str)
        or not project_path.strip("/")
        or collection not in {"issues", "merge_requests"}
        or not positive(iid)
    ):
        return None
    parts = project_path.strip("/").split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None
    encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in parts)
    return f"https://{host}/{encoded_path}/-/{collection}/{iid}"


def canonical_merge_request_url(host: str, merge_request: dict[str, Any]) -> str | None:
    iid = merge_request.get("iid")
    if not positive(iid):
        return None
    references = merge_request.get("references")
    full_reference = references.get("full") if isinstance(references, dict) else None
    reference_url = canonical_full_reference_url(host, full_reference, "!", "merge_requests", iid)
    web_url = merge_request.get("web_url")
    web_candidate = canonical_item_web_url(host, web_url, "merge_requests", iid)
    if full_reference is not None and reference_url is None:
        return None
    if web_url is not None and web_candidate is None:
        return None
    if reference_url is not None and web_candidate is not None and reference_url != web_candidate:
        return None
    return reference_url or web_candidate


def canonical_same_host_path(host: str, web_url: str) -> str | None:
    try:
        parsed = urllib.parse.urlsplit(web_url)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.hostname.casefold() != host.casefold()
        or port not in {None, 443}
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    return urllib.parse.unquote(parsed.path).rstrip("/")


def canonical_full_reference_url(
    host: str, value: object, sigil: str, collection: str, iid: int
) -> str | None:
    if not isinstance(value, str) or sigil not in value:
        return None
    project_path, reference_iid = value.rsplit(sigil, 1)
    if not reference_iid.isdigit() or int(reference_iid) != iid:
        return None
    return canonical_project_item_url(host, project_path, collection, iid)


def canonical_item_web_url(host: str, value: object, collection: str, iid: int) -> str | None:
    if not isinstance(value, str):
        return None
    decoded_path = canonical_same_host_path(host, value)
    if decoded_path is None:
        return None
    for suffix in (f"/-/{collection}/{iid}", f"/{collection}/{iid}"):
        if decoded_path.endswith(suffix):
            return canonical_project_item_url(host, decoded_path[: -len(suffix)], collection, iid)
    return None


def canonical_linked_issue_url(host: str, issue: dict[str, Any]) -> str | None:
    iid = issue.get("iid")
    if not positive(iid):
        return None
    references = issue.get("references")
    full_reference = references.get("full") if isinstance(references, dict) else None
    reference_url = canonical_full_reference_url(host, full_reference, "#", "issues", iid)
    web_url = issue.get("web_url")
    web_candidate = canonical_item_web_url(host, web_url, "issues", iid)
    if full_reference is not None and reference_url is None:
        return None
    if web_url is not None and web_candidate is None:
        return None
    if reference_url is not None and web_candidate is not None and reference_url != web_candidate:
        return None
    return reference_url or web_candidate


def is_plain_text_reference_value(value: str) -> bool:
    if re.search(r"(?:\b[a-z][a-z0-9+.-]*://|mailto:|\bwww\.)", value, re.IGNORECASE):
        return False
    if any(character in value for character in "`[]<>*_~"):
        return False
    if "\\" in value or "|" in value or re.search(r"[ \t]{2,}\r?\n", value):
        return False
    if re.search(r"(?m)^ {0,3}(?:=+|-{3,})[ \t]*$", value):
        return False
    return not re.search(
        r"(?m)^(?: {4}|\t| {0,3}(?:#{1,6}(?:[ \t]+|$)|>|[-+][ \t]+|\d+[.)][ \t]+|`{3,}|~{3,}))",
        value,
    )


def link_summary_references(value: str, references: dict[str, dict[int, str]]) -> str:
    if not is_plain_text_reference_value(value):
        return value
    pattern = re.compile(r"(?<![\w/\\])([#!])([1-9][0-9]*)(?![\w/\\])")

    def replace(match: re.Match[str]) -> str:
        kind, iid_text = match.groups()
        url = references[kind].get(int(iid_text))
        return f"[{kind}{iid_text}]({url})" if url else match.group(0)

    return pattern.sub(replace, value)


def markdown_link_label(value: str) -> str:
    normalized = " ".join(value.split())
    return (
        normalized.replace("\\", "\\\\")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def issue_summary_link(entry: dict[str, str]) -> str:
    label = markdown_link_label(f"#{entry['iid']} {entry['title']}")
    return f"[{label}]({entry['url']})"


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
    questions = validate_questions(collection, analysis.get("questions", []), items)
    top_five, parallel_groups = validate_execution_plan(
        analysis.get("top_five", []), analysis.get("parallel_groups", []), items
    )
    reports = private_directory(root / "reports")
    report_entries: list[dict[str, str]] = []
    uncovered: list[dict[str, str]] = []
    analysis_index = load_analysis_index(root)["items"]
    for item in items:
        target = item["evidence"]["target"]
        context = collection["context"].get(f"{target['hostname']}:{target['project_id']}")
        if not isinstance(context, dict) or not isinstance(context.get("current_user"), dict):
            raise WorkflowError("authenticated GitLab user evidence is unavailable")
        commands = commands_for(item, context["current_user"], locale)
        issue = read_object(Path(item["evidence"]["evidence_path"]), "issue evidence")["issue"]
        canonical_url = canonical_project_item_url(
            target["hostname"], context.get("project_path"), "issues", target["iid"]
        )
        if canonical_url is None:
            raise WorkflowError("canonical issue URL is unavailable")
        uncovered.extend(
            {
                "issue": canonical_url,
                "kind": labels[f"action_{entry['kind']}"],
                "reason": entry["instruction"],
            }
            for entry in commands
            if "instruction" in entry
        )
        report = reports / f"{target['hostname']}-{target['project_id']}-{target['iid']}.md"
        report_body = item_markdown(item, commands, locale, canonical_url).encode()
        atomic_write(report, versioned_markdown(report, report_body))
        _drop_issue_memory(
            target,
            str(issue.get("title") or item["evidence"]["url"]),
            str(item["release_plan"]["decision"]["status"]),
            str(item["release_plan"]["decision"]["rationale"]),
        )
        report_entries.append(
            {
                "url": canonical_url,
                "report": str(report),
                "iid": str(target["iid"]),
                "title": str(issue.get("title") or item["evidence"]["url"]),
                "decision": item["release_plan"]["decision"]["status"],
                "reason": item["release_plan"]["decision"]["rationale"],
                "next_step": item["agent_recommendation"]["proposal"],
            }
        )
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
        "schema": "task-triage/analysis/v5",
        "created_at": datetime.now(UTC).isoformat(),
        "collection_digest": collection_digest,
        "items": [
            {key: value for key, value in item.items() if key != "evidence"} for item in items
        ],
        "top_five": top_five,
        "parallel_groups": parallel_groups,
        "questions": questions,
        "external_mutations": False,
    }
    pending_planning = [
        item for item in items if item["release_plan"]["planning_verdict"] != "ready"
    ]
    active_requests = [
        (item, request)
        for item in items
        for request in item["information_requests"]
        if request["action"] != "none"
    ]
    pending_request_items = [
        item
        for item in items
        if any(request["action"] != "none" for request in item["information_requests"])
    ]
    complete = collection["complete"] and not artifact_value["questions"]
    follow_up_pending = bool(pending_planning or active_requests)
    artifact, analysis_digest = write_artifact(root, "analysis", artifact_value)
    write_json(
        root / "analysis-index.json",
        {"schema": ANALYSIS_INDEX_SCHEMA, "items": analysis_index},
    )
    references = summary_reference_maps(collection, items)

    entries = {
        item["evidence"]["evidence_digest"]: entry
        for item, entry in zip(items, report_entries, strict=True)
    }

    def question_entry(question: dict[str, Any]) -> dict[str, str]:
        return entries[question["evidence_digest"]]

    def plan_entry(evidence_digest: str) -> dict[str, str]:
        return entries[evidence_digest]

    top_markdown = markdown_list(
        [
            f"{issue_summary_link(plan_entry(value['evidence_digest']))} - "
            f"{link_summary_references(value['rationale'], references)}"
            for value in top_five
        ],
        locale,
    )
    parallel_markdown = markdown_list(
        [
            f"{', '.join(issue_summary_link(plan_entry(digest_value)) for digest_value in value['evidence_digests'])} - "
            f"{link_summary_references(value['rationale'], references)}"
            for value in parallel_groups
        ],
        locale,
    )

    def linked_question_field(question: dict[str, Any], field: str) -> str:
        return link_summary_references(question[field], references)

    def question_options(question: dict[str, Any]) -> str:
        return "; ".join(
            f"{link_summary_references(option['label'], references)}: "
            f"{link_summary_references(option['description'], references)}"
            for option in question["options"]
        )

    def issue_detail(item: dict[str, Any], reason: str) -> str:
        entry = entries[item["evidence"]["evidence_digest"]]
        return f"{issue_summary_link(entry)}: {link_summary_references(reason, references)}"

    collection_error_details = "; ".join(
        f"{error['target']}: {error['message']}" for error in collection["errors"]
    )
    question_details = "; ".join(
        f"{issue_summary_link(question_entry(question))}: "
        f"{labels['question_evidence']}: {linked_question_field(question, 'evidence')}; "
        f"{labels['missing_decision']}: {linked_question_field(question, 'decision')}; "
        f"{labels['why_now']}: {linked_question_field(question, 'why_now')}; "
        f"{labels['planning_effect']}: {linked_question_field(question, 'planning_effect')}"
        for question in questions
    )
    planning_details = "; ".join(
        issue_detail(
            item,
            f"{item['release_plan']['decision']['rationale']} "
            f"{item['release_plan']['milestone']['rationale']}",
        )
        for item in pending_planning
    )
    request_details = "; ".join(
        issue_detail(
            item,
            "; ".join(
                request["rationale"]
                for request in item["information_requests"]
                if request["action"] != "none"
            ),
        )
        for item in pending_request_items
    )
    uncovered_details = "; ".join(
        f"{entry['issue']}: {entry['kind']} - {entry['reason']}" for entry in uncovered
    )

    summary_lines = [
        f"# {labels['summary']}",
        "",
        f"- {labels['analysis_status']}: {labels['complete'] if complete else labels['partial']}",
        f"- {labels['follow_up_status']}: {labels['pending'] if follow_up_pending else labels['clear']}",
        f"- {labels['collection']}: `{collection_digest}`",
        f"- {labels['analysis']}: `{analysis_digest}`",
        f"- {labels['collection_errors']}: {len(collection['errors'])}"
        + (f" - {collection_error_details}" if collection_error_details else ""),
        f"- {labels['unanswered_questions']}: {len(questions)}"
        + (f" - {question_details}" if question_details else ""),
        f"- {labels['planning_pending']}: {len(pending_planning)}"
        + (f" - {planning_details}" if planning_details else ""),
        f"- {labels['requests_pending']}: {len(active_requests)}; "
        f"{labels['request_issues']}: {len(pending_request_items)}"
        + (f" - {request_details}" if request_details else ""),
        f"- {labels['uncovered']}: {len(uncovered)}"
        + (f" - {uncovered_details}" if uncovered_details else ""),
        "",
        f"## {labels['first']}",
        "",
        top_markdown,
        "",
        f"## {labels['parallel']}",
        "",
        parallel_markdown,
        "",
        f"## {labels['questions']}",
        "",
        markdown_list(
            [
                f"{issue_summary_link(question_entry(question))} - "
                f"{linked_question_field(question, 'tldr')} "
                f"{labels['question_evidence']}: {linked_question_field(question, 'evidence')}; "
                f"{labels['missing_decision']}: {linked_question_field(question, 'decision')}; "
                f"{labels['why_now']}: {linked_question_field(question, 'why_now')}; "
                f"{labels['planning_effect']}: "
                f"{linked_question_field(question, 'planning_effect')}; "
                f"{labels['recommendation']}: "
                f"{link_summary_references(question['recommendation']['option'], references)} - "
                f"{link_summary_references(question['recommendation']['rationale'], references)}; "
                f"{labels['options']}: {question_options(question)}; "
                f"{labels['fallback']}: "
                f"{question['fallback']['participant'] if question['fallback'] else labels['none']}"
                for question in questions
            ],
            locale,
        ),
        "",
        f"## {labels['reports']}",
        "",
    ]

    def append_report_entries(values: list[dict[str, str]]) -> None:
        if not values:
            summary_lines.extend([f"- {labels['none']}", ""])
            return
        for entry in values:
            reason = link_summary_references(entry["reason"], references)
            next_step = link_summary_references(entry["next_step"], references)
            summary_lines.append(
                f"- {issue_summary_link(entry)} - {labels['reason']}: {reason} "
                f"{labels['next_step']}: {next_step} "
                f"[{labels['report']}]({Path(entry['report']).as_uri()})"
            )
        summary_lines.append("")

    planning_ready = {
        item["evidence"]["evidence_digest"]: item["release_plan"]["planning_verdict"] == "ready"
        for item in items
    }
    entry_ready = {
        entry["report"]: planning_ready[item["evidence"]["evidence_digest"]]
        for item, entry in zip(items, report_entries, strict=True)
    }
    for decision in DECISIONS:
        summary_lines.extend([f"### {labels['decision_' + decision]}", ""])
        decision_entries = [entry for entry in report_entries if entry["decision"] == decision]
        if decision == "accepted":
            summary_lines.extend([f"#### {labels['decision_accepted_ready']}", ""])
            append_report_entries(
                [entry for entry in decision_entries if entry_ready[entry["report"]]]
            )
            summary_lines.extend([f"#### {labels['decision_accepted_pending']}", ""])
            append_report_entries(
                [entry for entry in decision_entries if not entry_ready[entry["report"]]]
            )
            continue
        append_report_entries(decision_entries)
    summary = root / "triage-summary.md"
    atomic_write(summary, versioned_markdown(summary, "\n".join(summary_lines).encode()))
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
        "follow_up_status": "pending" if follow_up_pending else "clear",
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
                    "mutation_outcome": "none",
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
