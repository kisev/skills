"""Read-only exact collection for mr-review.

The runtime is a helper: this module fetches the merge request, its diff,
discussions, pipelines, and linked issues through read-only ``glab api`` GET
requests, binds every result to the exact base, start, and head revisions, and
records completeness instead of treating absence as evidence. It never writes
to GitLab and never judges content.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote as urlquote

from reviewmatic.portable.portable_gitlab import contract

if TYPE_CHECKING:
    from collections.abc import Sequence

SCHEMA = "mr-review/context/v1"
MAX_PAGES = 100


def _text(value: object, *, redact: bool = True) -> str:
    text = value if isinstance(value, str) else ""
    return contract.redact(text) if redact else text


def _redacted(value: object) -> object:
    """Recursively redact every string in a GitLab payload."""
    if isinstance(value, str):
        return contract.redact(value)
    if isinstance(value, list):
        return [_redacted(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _redacted(item) for key, item in value.items()}
    return value


def _component(
    items: Sequence[object] | None = None,
    *,
    complete: bool = True,
    errors: list[str] | None = None,
    pages: int = 0,
    truncated: bool = False,
) -> dict[str, Any]:
    return {
        "items": list(items or []),
        "complete": complete,
        "errors": errors or [],
        "pages": pages,
        "truncated": truncated,
    }


def _paged(hostname: str, endpoint: str) -> dict[str, Any]:
    result = contract.paginated(hostname, endpoint, max_pages=MAX_PAGES)
    return _component(
        cast("list[object]", result.get("items") or []),
        complete=bool(result.get("complete")),
        errors=[_text(item) for item in cast("list[object]", result.get("errors") or [])],
        pages=int(cast("int", result.get("pages") or 0)),
        truncated=bool(result.get("truncated")),
    )


def _read_json(hostname: str, endpoint: str) -> object:
    return contract.glab_json(hostname, endpoint)


def _dict(value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _list(value: object) -> list[object]:
    return cast("list[object]", value) if isinstance(value, list) else []


def _mr_object(hostname: str, project_id: int, iid: int) -> dict[str, Any]:
    return _dict(_read_json(hostname, f"projects/{project_id}/merge_requests/{iid}"))


def _exact_refs(merge_request: dict[str, Any]) -> dict[str, Any]:
    refs = _dict(merge_request.get("diff_refs"))
    values = {name: refs.get(name) for name in ("base_sha", "start_sha", "head_sha")}
    missing = [name for name, value in values.items() if not isinstance(value, str) or not value]
    return {
        "base_sha": values["base_sha"] if isinstance(values["base_sha"], str) else None,
        "start_sha": values["start_sha"] if isinstance(values["start_sha"], str) else None,
        "head_sha": values["head_sha"] if isinstance(values["head_sha"], str) else None,
        "missing": missing,
    }


def _changed_files(
    hostname: str, project_id: int, iid: int, refs: dict[str, Any]
) -> dict[str, Any]:
    try:
        changes = _dict(_read_json(hostname, f"projects/{project_id}/merge_requests/{iid}/changes"))
    except contract.WorkflowError as error:
        return _component(complete=False, errors=[str(error)], truncated=True)
    overflow = changes.get("overflow") is True or changes.get("changes_count") == "1000+"
    if overflow:
        return _component(
            complete=False,
            errors=["GitLab changed-files response overflowed"],
            truncated=True,
        )
    api_refs = _dict(changes.get("diff_refs"))
    if any(api_refs.get(name) != refs.get(name) for name in ("base_sha", "start_sha", "head_sha")):
        return _component(
            complete=False,
            errors=["changed-files revisions do not match the merge request revisions"],
            truncated=True,
        )
    items = [_redacted(item) for item in _list(changes.get("changes")) if isinstance(item, dict)]
    return _component(items, pages=1)


def _pipeline_checks(
    hostname: str, project_id: int, iid: int, head_sha: str | None
) -> dict[str, Any]:
    pipelines = _paged(hostname, f"projects/{project_id}/merge_requests/{iid}/pipelines")
    if not pipelines["complete"]:
        return {
            "pipelines": pipelines,
            "status": "unknown",
            "failed_jobs": [],
            "complete": False,
            "errors": pipelines["errors"],
        }
    head_pipeline: dict[str, Any] | None = None
    for item in cast("list[object]", pipelines["items"]):
        pipeline = _dict(item)
        if head_sha is not None and pipeline.get("sha") == head_sha:
            pipeline_id = pipeline.get("id")
            if isinstance(pipeline_id, int) and (
                head_pipeline is None or pipeline_id > cast("int", head_pipeline["id"])
            ):
                head_pipeline = pipeline
    if head_pipeline is None:
        return {
            "pipelines": pipelines,
            "status": "none",
            "failed_jobs": [],
            "complete": True,
            "errors": [],
        }
    pipeline_id = head_pipeline.get("id")
    failed: list[dict[str, Any]] = []
    errors: list[str] = []
    complete = True
    if isinstance(pipeline_id, int):
        jobs = _paged(hostname, f"projects/{project_id}/pipelines/{pipeline_id}/jobs")
        complete = jobs["complete"]
        errors = jobs["errors"]
        for item in cast("list[object]", jobs["items"]):
            job = _dict(item)
            if job.get("status") in {"failed", "canceled"}:
                failed.append(
                    {
                        "name": _text(job.get("name")),
                        "stage": _text(job.get("stage")),
                        "status": _text(job.get("status")),
                        "web_url": _text(job.get("web_url")),
                    }
                )
    return {
        "pipelines": pipelines,
        "pipeline": {
            "id": pipeline_id,
            "status": _text(head_pipeline.get("status")),
            "sha": _text(head_pipeline.get("sha")),
            "web_url": _text(head_pipeline.get("web_url")),
        },
        "status": _text(head_pipeline.get("status")) or "unknown",
        "failed_jobs": failed,
        "complete": complete,
        "errors": errors,
    }


def _linked_issues(hostname: str, project_id: int, iid: int) -> dict[str, Any]:
    closes = _paged(hostname, f"projects/{project_id}/merge_requests/{iid}/closes_issues")
    issues: list[dict[str, Any]] = []
    errors = list(closes["errors"])
    complete = closes["complete"]
    for item in cast("list[object]", closes["items"]):
        summary = _dict(item)
        issue_project = summary.get("project_id")
        issue_iid = summary.get("iid")
        if not isinstance(issue_project, int) or not isinstance(issue_iid, int):
            complete = False
            errors.append("a closing issue reference is incomplete")
            continue
        try:
            issue = _dict(_read_json(hostname, f"projects/{issue_project}/issues/{issue_iid}"))
        except contract.WorkflowError as error:
            complete = False
            errors.append(str(error))
            continue
        issues.append(
            {
                "project_id": issue_project,
                "iid": issue_iid,
                "title": _text(issue.get("title")),
                "description": _text(issue.get("description")),
                "labels": [_text(label) for label in _list(issue.get("labels"))],
                "state": _text(issue.get("state")),
                "web_url": _text(issue.get("web_url")),
            }
        )
    return _component(issues, complete=complete, errors=errors)


def _local_refs(repo_root: str | None, refs: dict[str, Any]) -> dict[str, Any]:
    if repo_root is None:
        return {"provided": False, "base_sha": False, "head_sha": False}
    present: dict[str, bool] = {}
    for name in ("base_sha", "head_sha"):
        sha = refs.get(name)
        if not isinstance(sha, str) or not sha:
            present[name] = False
            continue
        try:
            completed = subprocess.run(
                ["git", "-C", repo_root, "cat-file", "-e", f"{sha}^{{commit}}"],
                capture_output=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise contract.WorkflowError("the review checkout could not be read") from None
        present[name] = completed.returncode == 0
    return {"provided": True, "base_sha": present["base_sha"], "head_sha": present["head_sha"]}


def collect(url: str, *, repo_root: str | None = None) -> dict[str, Any]:
    """Collect one merge request read-only and bind every result to exact refs."""
    target = contract.parse_target(url, {"merge_requests"})
    hostname = str(target["hostname"])
    project_path = str(target["project_path"])
    iid = int(cast("int", target["iid"]))
    project = _dict(_read_json(hostname, f"projects/{urlquote(project_path, safe='')}"))
    project_id = project.get("id")
    if not isinstance(project_id, int):
        raise contract.WorkflowError("GitLab project identity is incomplete")
    merge_request = _mr_object(hostname, project_id, iid)
    if merge_request.get("iid") not in {None, iid}:
        raise contract.WorkflowError("GitLab merge request response is incomplete")
    refs = _exact_refs(merge_request)
    refs_complete = not refs["missing"]
    changed = _changed_files(hostname, project_id, iid, refs)
    if not refs_complete:
        changed = _component(
            cast("list[object]", changed["items"]),
            complete=False,
            errors=[
                *cast("list[str]", changed["errors"]),
                "exact base, start, and head revisions are unavailable",
            ],
            pages=int(cast("int", changed["pages"])),
            truncated=True,
        )
    if isinstance(merge_request.get("sha"), str) and merge_request["sha"] != refs["head_sha"]:
        changed = _component(
            cast("list[object]", changed["items"]),
            complete=False,
            errors=[
                *cast("list[str]", changed["errors"]),
                "the merge request sha does not match the diff head",
            ],
            pages=int(cast("int", changed["pages"])),
            truncated=True,
        )
    discussions = _paged(hostname, f"projects/{project_id}/merge_requests/{iid}/discussions")
    discussions["items"] = [_redacted(item) for item in discussions["items"]]
    checks = _pipeline_checks(hostname, project_id, iid, cast("str | None", refs["head_sha"]))
    linked = _linked_issues(hostname, project_id, iid)
    local = _local_refs(repo_root, refs)
    components = {
        "project": True,
        "merge_request": True,
        "exact_refs": refs_complete,
        "changed_files": bool(changed["complete"]),
        "discussions": bool(discussions["complete"]),
        "pipelines": bool(checks["complete"]),
        "linked_issues": bool(linked["complete"]),
    }
    complete = all(components.values()) and (
        not local["provided"] or all(local.get(name) for name in ("base_sha", "head_sha"))
    )
    return {
        "schema": SCHEMA,
        "status": "complete" if complete else "partial",
        "external_mutations": False,
        "redacted": True,
        "collected_at": datetime.now(UTC).isoformat(),
        "target": {
            "url": url,
            "hostname": hostname,
            "project_path": project_path,
            "project_id": project_id,
            "iid": iid,
        },
        "merge_request": {
            "title": _text(merge_request.get("title")),
            "description": _text(merge_request.get("description")),
            "state": _text(merge_request.get("state")),
            "labels": [_text(label) for label in _list(merge_request.get("labels"))],
            "source_branch": _text(merge_request.get("source_branch")),
            "target_branch": _text(merge_request.get("target_branch")),
            "web_url": _text(merge_request.get("web_url")),
            "author": _dict(merge_request.get("author")),
        },
        "refs": {
            "base_sha": refs["base_sha"],
            "start_sha": refs["start_sha"],
            "head_sha": refs["head_sha"],
        },
        "changed_files": changed,
        "discussions": discussions,
        "pipelines": checks["pipelines"],
        "checks": {
            "pipeline": checks.get("pipeline"),
            "status": checks["status"],
            "failed_jobs": checks["failed_jobs"],
        },
        "linked_issues": linked,
        "local_checkout": local,
        "components_complete": components,
        "retrieval_complete": complete,
    }
