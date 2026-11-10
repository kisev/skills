"""Freshness revalidation for one collected merge request snapshot.

The runtime re-reads only the merge request head and reports whether the
snapshot still describes the current head. It never re-collects the full
context; that is a fresh ``collect``.
"""

from __future__ import annotations

from typing import Any, cast
from urllib.parse import quote as urlquote

from reviewmatic.portable.portable_gitlab import contract


def revalidate(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Compare the snapshot's exact refs with the current merge request head."""
    target = snapshot.get("target")
    refs = snapshot.get("refs")
    if not isinstance(target, dict) or not isinstance(refs, dict):
        raise contract.WorkflowError("the snapshot has no merge request target or exact refs")
    if snapshot.get("schema") != "mr-review/context/v1":
        raise contract.WorkflowError("the snapshot schema is not mr-review/context/v1")
    hostname = target.get("hostname")
    iid = target.get("iid")
    reviewed_head = refs.get("head_sha")
    if not isinstance(hostname, str) or not isinstance(iid, int):
        raise contract.WorkflowError("the snapshot target is incomplete")
    if not isinstance(reviewed_head, str) or not reviewed_head:
        raise contract.WorkflowError("the snapshot has no reviewed head")
    project_path = target.get("project_path")
    if not isinstance(project_path, str) or not project_path:
        raise contract.WorkflowError("the snapshot project path is incomplete")
    project = contract.glab_json(hostname, f"projects/{urlquote(project_path, safe='')}")
    current_project = cast("dict[str, Any]", project) if isinstance(project, dict) else {}
    current_project_id = current_project.get("id")
    if not isinstance(current_project_id, int):
        raise contract.WorkflowError("the GitLab project identity is incomplete")
    merge_request = contract.glab_json(
        hostname, f"projects/{current_project_id}/merge_requests/{iid}"
    )
    current = cast("dict[str, Any]", merge_request) if isinstance(merge_request, dict) else {}
    current_head = current.get("sha")
    if not isinstance(current_head, str) or not current_head:
        raise contract.WorkflowError("the current merge request head is unavailable")
    if current_head == reviewed_head:
        return {
            "status": "unchanged",
            "reviewed_head": reviewed_head,
            "current_head": current_head,
            "external_mutations": False,
        }
    return {
        "status": "stale",
        "reviewed_head": reviewed_head,
        "current_head": contract.redact(current_head),
        "instruction": (
            "the merge request head moved since collection; run collect again and review "
            "the current range"
        ),
        "external_mutations": False,
    }
