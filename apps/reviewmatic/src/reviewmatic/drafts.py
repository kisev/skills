"""Draft-note command generation for mr-review.

The runtime generates one non-interactive shell block of ``glab api`` calls
that create GitLab draft notes. The block starts with one head check against
the reviewed head and stops before creating a draft when the head moved. No
publish command exists: the human edits and submits the drafts in the GitLab
UI.
"""

from __future__ import annotations

import re
from typing import Any, cast

from reviewmatic.portable.portable_gitlab import contract

SHA_RE = re.compile(r"[0-9a-f]{40}")
HOST_RE = re.compile(r"[a-z0-9.-]+")


def _shell(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _text(item: dict[str, Any], key: str, *, required: bool = True) -> str:
    value = item.get(key)
    if not isinstance(value, str) or (required and not value.strip()):
        raise contract.WorkflowError(f"draft field {key} must be a non-empty string")
    return value


def _sha(item: dict[str, Any], key: str) -> str:
    value = _text(item, key)
    if SHA_RE.fullmatch(value) is None:
        raise contract.WorkflowError(f"draft field {key} must be an exact 40-character SHA")
    return value


def _line(item: dict[str, Any], key: str) -> int | None:
    value = item.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise contract.WorkflowError(f"draft field {key} must be a positive integer")
    return value


def _draft_command(hostname: str, project_id: int, iid: int, args: list[str]) -> str:
    header = (
        f"glab api --hostname {hostname} --method POST "
        f"projects/{project_id}/merge_requests/{iid}/drafts"
    )
    return " \\\n  ".join([header, *args])


def _position(item: dict[str, Any], head_sha: str) -> dict[str, str]:
    old_line = _line(item, "old_line")
    new_line = _line(item, "new_line")
    if old_line is None and new_line is None:
        raise contract.WorkflowError("a positioned draft needs old_line or new_line")
    position = {
        "position_type": "text",
        "base_sha": _sha(item, "base_sha"),
        "start_sha": _sha(item, "start_sha"),
        "head_sha": head_sha,
        "old_path": _text(item, "old_path"),
        "new_path": _text(item, "new_path"),
    }
    if new_line is not None:
        position["new_line"] = str(new_line)
    if old_line is not None:
        position["old_line"] = str(old_line)
    return position


def build_drafts(payload: dict[str, Any]) -> dict[str, Any]:
    """Render the head check and the draft-note block from one manager input."""
    hostname = str(payload.get("hostname") or payload.get("host") or "")
    if HOST_RE.fullmatch(hostname) is None:
        raise contract.WorkflowError("the draft hostname must be a bare GitLab host")
    project_id = payload.get("project_id")
    iid = payload.get("mr_iid")
    if not isinstance(project_id, int) or isinstance(project_id, bool) or project_id <= 0:
        raise contract.WorkflowError("the draft project_id must be a positive integer")
    if not isinstance(iid, int) or isinstance(iid, bool) or iid <= 0:
        raise contract.WorkflowError("the draft mr_iid must be a positive integer")
    head_sha = _text(payload, "head_sha")
    if SHA_RE.fullmatch(head_sha) is None:
        raise contract.WorkflowError("the draft head_sha must be an exact 40-character SHA")
    reply_support = payload.get("draft_reply_support", True)
    if not isinstance(reply_support, bool):
        raise contract.WorkflowError("draft_reply_support must be boolean")

    commands: list[str] = []
    positioned = 0
    general = 0
    replies = 0
    findings = payload.get("findings") or []
    if not isinstance(findings, list):
        raise contract.WorkflowError("draft findings must be a list")
    for item in cast("list[object]", findings):
        if not isinstance(item, dict):
            raise contract.WorkflowError("each draft finding must be an object")
        finding = cast("dict[str, Any]", item)
        args = [f"-f {_shell('body=' + _text(finding, 'body'))}"]
        if any(
            finding.get(key) is not None for key in ("old_line", "new_line", "old_path", "new_path")
        ):
            for key, value in _position(finding, head_sha).items():
                args.append(f"-f {_shell(f'position[{key}]={value}')}")
            positioned += 1
        else:
            general += 1
        commands.append(_draft_command(hostname, project_id, iid, args))

    notes = payload.get("general_notes") or []
    if not isinstance(notes, list):
        raise contract.WorkflowError("draft general_notes must be a list")
    for note in cast("list[object]", notes):
        if not isinstance(note, str) or not note.strip():
            raise contract.WorkflowError("each general draft note must be a non-empty string")
        commands.append(_draft_command(hostname, project_id, iid, [f"-f {_shell('body=' + note)}"]))
        general += 1

    discussion_replies = payload.get("discussion_replies") or []
    if not isinstance(discussion_replies, list):
        raise contract.WorkflowError("draft discussion_replies must be a list")
    for item in cast("list[object]", discussion_replies):
        if not isinstance(item, dict):
            raise contract.WorkflowError("each discussion reply must be an object")
        reply = cast("dict[str, Any]", item)
        body = _text(reply, "body")
        discussion = _text(reply, "discussion_id")
        if reply_support:
            args = [
                f"-f {_shell('body=' + body)}",
                f"-f {_shell('in_reply_to_discussion_id=' + discussion)}",
            ]
        else:
            args = [f"-f {_shell('body=' + body)}"]
        commands.append(_draft_command(hostname, project_id, iid, args))
        replies += 1

    check = "\n".join(
        [
            "set -eu",
            f"reviewed_head={_shell(head_sha)}",
            (
                "current_head=$(glab api --hostname "
                f"{hostname} projects/{project_id}/merge_requests/{iid} --jq '.sha')"
            ),
            'if [ "$current_head" != "$reviewed_head" ]; then',
            (
                '  echo "mr-review: the merge request head moved from '
                '$reviewed_head to $current_head; no draft was created" >&2'
            ),
            "  exit 1",
            "fi",
        ]
    )
    shell = check + "\n" + "\n".join(commands) + ("\n" if commands else "")
    return {
        "status": "ok",
        "shell": shell,
        "head_sha": head_sha,
        "positioned": positioned,
        "general": general,
        "replies": replies,
        "drafts": len(commands),
        "external_mutations": False,
    }
