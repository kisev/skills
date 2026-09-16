#!/usr/bin/env python3
"""Collect role, thread, and exact local Git context for one MR review."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import fcntl
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Iterator, cast
from urllib.parse import quote

if TYPE_CHECKING:
    from shared.references.portable_gitlab import contract as portable
else:
    from portable_runtime import contract as portable


INCREMENTAL_CONTRACT_VERSION = 1
REVIEW_CONTRACT_VERSION = 4
BASELINE_NAME = "review-baseline.json"
PROGRESS_NAME = "review-current.json"
REVIEW_EVIDENCE_NAME = "review-evidence.json"
REVIEW_STAGES = {
    "prepared",
    "context_ready",
    "critic_missing",
    "finalize_missing",
    "decision_missing",
    "content_missing",
    "plan_ready",
    "stale",
}
REVIEW_MODES = {"fast", "normal", "deep", "incremental", "unchanged"}
SUPPORTED_LOCALES = {"en", "ru"}
PUBLICATION_MARKER_RE = re.compile(
    r"<!-- code-review:id=(?P<id>[A-Za-z0-9][A-Za-z0-9._-]{0,63});"
    r"revision=(?P<revision>[1-9][0-9]*);kind=(?P<kind>finding|thread|issue);"
    r"target=(?P<target>[a-f0-9]{16}) -->"
)
PUBLICATION_MARKER_PREFIX = "<!-- code-review:"
SUGGESTION_RE = re.compile(
    r"^```suggestion(?::-(?P<before>[0-9]+)\+(?P<after>[0-9]+))?\r?\n"
    r"(?P<replacement>.*?)^```[ \t]*$",
    re.DOTALL | re.MULTILINE,
)
SUGGESTION_OPENER_RE = re.compile(r"^```suggestion[^\r\n]*$", re.MULTILINE)
PREVIOUS_FINDING_STATUSES = {"active", "fixed", "withdrawn", "changed", "unverified"}


def runner_action(
    command: str, *arguments: str, required_inputs: tuple[str, ...] = ()
) -> dict[str, Any]:
    argv = [sys.executable, str(Path(__file__).resolve().with_name("review_mr.py")), command]
    argv.extend(arguments)
    return {
        "command": " ".join(shlex.quote(value) for value in argv),
        "argv": argv,
        "required_inputs": list(required_inputs),
    }


def empty_progress(
    evidence_path: Path,
    evidence_digest: str,
    *,
    repo_root: str | None = None,
    mode: str | None = None,
    locale: str | None = None,
    incremental: str = "auto",
) -> dict[str, Any]:
    return {
        "schema": "code-review/progress/v1",
        "stage": "prepared",
        "evidence_path": str(evidence_path),
        "evidence_digest": evidence_digest,
        "repo_root": repo_root,
        "context_path": None,
        "context_digest": None,
        "mode": mode,
        "locale": locale,
        "incremental": incremental,
        "critic_receipt_path": None,
        "critic_receipt_digest": None,
        "finalize_report_path": None,
        "finalize_report_digest": None,
        "decision_path": None,
        "decision_digest": None,
        "plan_path": None,
        "plan_digest": None,
        "updated_at": datetime.now(UTC).isoformat(),
    }


def validate_progress(value: object, root: Path) -> dict[str, Any]:
    required = set(empty_progress(root / "placeholder", "0" * 64))
    if not isinstance(value, dict) or set(value) != required:
        raise portable.WorkflowError("code-review progress has an invalid shape")
    if (
        value.get("schema") != "code-review/progress/v1"
        or value.get("stage") not in REVIEW_STAGES
        or not portable.is_digest(value.get("evidence_digest"))
        or value.get("mode") is not None
        and value.get("mode") not in REVIEW_MODES
        or value.get("locale") is not None
        and value.get("locale") not in SUPPORTED_LOCALES
        or value.get("incremental") not in {"auto", "off"}
        or value.get("repo_root") is not None
        and (
            not portable.nonempty_string(value.get("repo_root"))
            or not Path(cast(str, value["repo_root"])).is_absolute()
        )
        or not portable.nonempty_string(value.get("updated_at"))
    ):
        raise portable.WorkflowError("code-review progress is invalid")
    for prefix in ("evidence", "context", "critic_receipt", "finalize_report", "decision", "plan"):
        path_value = value.get(f"{prefix}_path")
        digest_value = value.get(f"{prefix}_digest")
        if (path_value is None) != (digest_value is None):
            raise portable.WorkflowError("code-review progress artifact binding is incomplete")
        if path_value is None:
            continue
        path = Path(str(path_value))
        if (
            not path.is_absolute()
            or not path.is_relative_to(root)
            or not portable.is_digest(digest_value)
        ):
            raise portable.WorkflowError("code-review progress artifact binding is unsafe")
    return cast(dict[str, Any], value)


def progress_path(root: Path) -> Path:
    return root / PROGRESS_NAME


def review_evidence_from_root(root: Path) -> tuple[Path, dict[str, Any]]:
    pointer = portable.exact_keys(
        portable.read_json(root / REVIEW_EVIDENCE_NAME, "current review evidence"),
        {"evidence_path", "evidence_digest"},
        "current review evidence",
    )
    digest = pointer["evidence_digest"]
    if not portable.is_digest(digest):
        raise portable.WorkflowError("current review evidence digest is invalid")
    source = portable.regular_file(Path(str(pointer["evidence_path"])), "review evidence")
    expected = root / "artifacts" / "evidence_snapshot" / f"{digest}.json"
    if source != expected or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise portable.WorkflowError("current review evidence binding changed")
    _, evidence = portable.artifact_payload(source, "evidence_snapshot")
    if evidence.get("profile") != "code-review":
        raise portable.WorkflowError("current review evidence has the wrong profile")
    return source, evidence


def load_progress(root: Path) -> dict[str, Any] | None:
    path = progress_path(root)
    if not path.exists() and not path.is_symlink():
        return None
    return validate_progress(portable.read_json(path, "code-review progress"), root)


def begin_review(
    evidence_path: str,
    evidence_digest: str,
    artifact_root: str,
    repo_root: str | None = None,
    mode: str = "normal",
    locale: str = "en",
    incremental: str = "auto",
) -> dict[str, Any]:
    root = portable.artifact_root(Path(artifact_root))
    source = portable.regular_file(Path(evidence_path), "review evidence")
    expected = root / "artifacts" / "evidence_snapshot" / f"{evidence_digest}.json"
    if source != expected or hashlib.sha256(source.read_bytes()).hexdigest() != evidence_digest:
        raise portable.WorkflowError("review evidence cannot initialize progress")
    if (
        mode not in {"fast", "normal", "deep"}
        or locale not in SUPPORTED_LOCALES
        or incremental not in {"auto", "off"}
    ):
        raise portable.WorkflowError("review mode or locale cannot initialize progress")
    resolved_repo = str(Path(repo_root).resolve()) if repo_root is not None else None
    value = empty_progress(
        source,
        evidence_digest,
        repo_root=resolved_repo,
        mode=mode,
        locale=locale,
        incremental=incremental,
    )
    current_path = root / REVIEW_EVIDENCE_NAME
    state_path = progress_path(root)
    with review_state_lock(root):
        if current_path.is_symlink() or state_path.is_symlink():
            raise portable.WorkflowError("review current-state paths must not be symbolic links")
        previous_current = current_path.read_bytes() if current_path.exists() else None
        previous_progress = state_path.read_bytes() if state_path.exists() else None
        try:
            portable.write_json(state_path, value)
            portable.write_json(
                current_path,
                {"evidence_path": str(source), "evidence_digest": evidence_digest},
            )
        except (OSError, UnicodeDecodeError, portable.WorkflowError):
            for path, previous in (
                (state_path, previous_progress),
                (current_path, previous_current),
            ):
                if previous is None:
                    path.unlink(missing_ok=True)
                else:
                    replace_private_bytes(path, previous)
            raise
    return value


def advance_progress(
    root: Path,
    stage: str,
    *,
    expected_stages: set[str] | None = None,
    expected: dict[str, object] | None = None,
    **changes: object,
) -> dict[str, Any]:
    if stage not in REVIEW_STAGES:
        raise portable.WorkflowError("code-review progress stage is invalid")
    with review_state_lock(root):
        path = progress_path(root)
        if path.exists() or path.is_symlink():
            current = validate_progress(portable.read_json(path, "code-review progress"), root)
        else:
            evidence_path, _ = review_evidence_from_root(root)
            evidence_digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
            current = empty_progress(evidence_path, evidence_digest)
        if expected_stages is not None and current["stage"] not in expected_stages:
            raise portable.WorkflowError("code-review progress changed during transition")
        if expected is not None and (
            not set(expected).issubset(current)
            or any(current[key] != value for key, value in expected.items())
        ):
            raise portable.WorkflowError("code-review progress binding changed during transition")
        unknown = set(changes) - set(current)
        if unknown:
            raise portable.WorkflowError("code-review progress update has unknown fields")
        value = {**current, **changes, "stage": stage, "updated_at": datetime.now(UTC).isoformat()}
        validate_progress(value, root)
        portable.write_json(path, value)
        return value


def localized_presentation(
    locale: str, role: str, verdict: str, incremental_mode: str
) -> dict[str, Any]:
    return portable.code_review_presentation(locale, role, verdict, incremental_mode)


def repository_root(value: str) -> Path:
    raw = Path(value)
    if raw.is_symlink():
        raise portable.WorkflowError("repository root must not be a symbolic link")
    root = raw.resolve()
    if not (root / ".git").exists():
        raise portable.WorkflowError("repository root must be a Git checkout")
    inside = str(portable.git_read(root, "rev-parse", "--is-inside-work-tree")).strip()
    if inside != "true":
        raise portable.WorkflowError("repository root must be a Git checkout")
    return root


def evidence_context(
    evidence_value: str | Path,
) -> tuple[Path, dict[str, Any], Path, str]:
    source = portable.regular_file(Path(evidence_value), "review evidence")
    _, evidence = portable.artifact_payload(source, "evidence_snapshot")
    if evidence.get("profile") != "code-review":
        raise portable.WorkflowError("review context requires code-review evidence")
    root = portable.artifact_root(Path(str(evidence.get("artifact_root", ""))))
    evidence_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    expected = root / "artifacts" / "evidence_snapshot" / f"{evidence_digest}.json"
    if source != expected:
        raise portable.WorkflowError("review evidence is not content-addressed")
    return source, evidence, root, evidence_digest


def stable_id(value: object) -> tuple[int, int | str]:
    if isinstance(value, bool):
        raise portable.WorkflowError("GitLab note or discussion has no stable ID")
    if isinstance(value, int):
        return 0, value
    if isinstance(value, str) and value.isdecimal():
        return 0, int(value)
    if isinstance(value, str) and value:
        return 1, value
    raise portable.WorkflowError("GitLab note or discussion has no stable ID")


def deduplicate(values: list[object], label: str) -> list[dict[str, Any]]:
    unique: dict[int | str, dict[str, Any]] = {}
    for value in values:
        if not isinstance(value, dict):
            raise portable.WorkflowError(f"GitLab {label} entry is not an object")
        item_id = value.get("id")
        stable_id(item_id)
        unique.setdefault(cast(int | str, item_id), value)
    return sorted(unique.values(), key=lambda item: stable_id(item.get("id")))


def username(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    result = value.get("username")
    return result if isinstance(result, str) and result else None


def publication_marker(value: str) -> dict[str, Any] | None:
    matches = list(PUBLICATION_MARKER_RE.finditer(value))
    if not matches:
        return None
    if len(matches) != 1 or value[matches[0].end() :].strip():
        raise portable.WorkflowError("code-review publication marker is malformed")
    match = matches[0]
    return {
        "id": match.group("id"),
        "revision": int(match.group("revision")),
        "kind": match.group("kind"),
        "target": match.group("target"),
    }


def marked_body(body: str, publication_id: str, revision: int, kind: str, target: str) -> str:
    if not portable.nonempty_string(body) or PUBLICATION_MARKER_PREFIX in body:
        raise portable.WorkflowError("publication body is empty or already contains a marker")
    marker = publication_marker_text(publication_id, revision, kind, target)
    if PUBLICATION_MARKER_RE.fullmatch(marker) is None:
        raise portable.WorkflowError("publication marker identity is invalid")
    return body.rstrip() + f"\n\n{marker}\n"


def publication_marker_text(publication_id: str, revision: int, kind: str, target: str) -> str:
    return (
        f"<!-- code-review:id={publication_id};revision={revision};kind={kind};target={target} -->"
    )


def collect_publication_markers(
    discussions: list[dict[str, Any]], notes: list[dict[str, Any]], current_username: str
) -> tuple[list[dict[str, Any]], list[str]]:
    markers: list[dict[str, Any]] = []
    errors: list[str] = []
    discussion_note_ids: set[str] = set()
    sources: list[tuple[dict[str, Any], object, bool, object]] = []
    note_urls = {str(note.get("id")): note.get("note_url") for note in notes}
    for discussion in discussions:
        discussion_id = discussion.get("id")
        root_note_id = discussion.get("root_note_id")
        for index, value in enumerate(cast(list[object], discussion.get("notes", []))):
            if isinstance(value, dict):
                discussion_note_ids.add(str(value.get("id")))
                sources.append((value, discussion_id, index == 0, root_note_id))
    sources.extend(
        (note, None, True, note.get("id"))
        for note in notes
        if str(note.get("id")) not in discussion_note_ids
    )
    for note, discussion_id, is_root, root_note_id in sources:
        if note.get("system") is True or username(note.get("author")) != current_username:
            continue
        body = note.get("body")
        if not isinstance(body, str) or PUBLICATION_MARKER_PREFIX not in body:
            continue
        try:
            marker = publication_marker(body)
        except portable.WorkflowError as exc:
            errors.append(f"note {note.get('id')}: {exc}")
            continue
        if marker is None:
            errors.append(f"note {note.get('id')}: code-review publication marker is malformed")
            continue
        markers.append(
            {
                **marker,
                "note_id": note.get("id"),
                "note_url": note_urls.get(str(note.get("id"))),
                "discussion_id": discussion_id,
                "author_username": current_username,
                "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
                "resource_type": "note",
                "is_root": is_root,
                "position": note.get("position")
                if isinstance(note.get("position"), dict)
                else None,
                "root_note_id": root_note_id,
                "resource_title": None,
                "resource_body": None,
            }
        )
    return sorted(markers, key=lambda item: (item["id"], item["revision"])), errors


def discussion_signature(value: dict[str, Any]) -> str:
    notes = []
    for note in cast(list[object], value.get("notes", [])):
        if not isinstance(note, dict) or note.get("system") is True:
            continue
        notes.append(
            {
                "id": note.get("id"),
                "body": note.get("body"),
                "author": username(note.get("author")),
                "resolved": note.get("resolved"),
                "resolved_by": username(note.get("resolved_by")),
                "position": note.get("position"),
            }
        )
    return json.dumps(
        {
            "id": value.get("id"),
            "resolved": value.get("root_resolved"),
            "position": value.get("root_position"),
            "notes": notes,
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def baseline_pointer(root: Path) -> tuple[dict[str, Any], dict[str, Any]] | None:
    pointer_path = root / BASELINE_NAME
    if not pointer_path.exists():
        return None
    pointer = portable.read_json(pointer_path, "code-review baseline")
    if set(pointer) != {
        "contract_version",
        "target",
        "plan_path",
        "plan_digest",
        "markdown_path",
        "markdown_digest",
        "updated_at",
    }:
        raise portable.WorkflowError("code-review baseline has an invalid shape")
    if pointer.get("contract_version") != INCREMENTAL_CONTRACT_VERSION:
        raise portable.WorkflowError("code-review baseline contract is incompatible")
    plan_path = Path(str(pointer.get("plan_path", "")))
    plan_digest = pointer.get("plan_digest")
    if not portable.is_digest(plan_digest):
        raise portable.WorkflowError("code-review baseline digest is invalid")
    expected = root / "artifacts" / "review_plan" / f"{plan_digest}.json"
    if plan_path.resolve() != expected.resolve():
        raise portable.WorkflowError("code-review baseline plan path is invalid")
    _, plan = portable.artifact_payload(plan_path, "review_plan")
    if hashlib.sha256(plan_path.read_bytes()).hexdigest() != plan_digest:
        raise portable.WorkflowError("code-review baseline plan digest changed")
    if (
        plan.get("complete") is not True
        or plan.get("review_contract_version") not in {1, 2, 3, REVIEW_CONTRACT_VERSION}
        or plan.get("target") != pointer.get("target")
    ):
        raise portable.WorkflowError("code-review baseline is incomplete or incompatible")
    markdown_path = Path(str(pointer.get("markdown_path", "")))
    if markdown_path != root / "review-publication.md" or not portable.is_digest(
        pointer.get("markdown_digest")
    ):
        raise portable.WorkflowError("code-review baseline Markdown identity is invalid")
    source = portable.regular_file(markdown_path, "code-review baseline Markdown")
    try:
        markdown = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise portable.WorkflowError("code-review baseline Markdown is unreadable") from exc
    if (
        hashlib.sha256(source.read_bytes()).hexdigest() != pointer["markdown_digest"]
        or plan.get("markdown") != markdown
    ):
        raise portable.WorkflowError("code-review baseline Markdown changed")
    return pointer, plan


def trusted_publication_markers(
    root: Path,
    evidence: dict[str, Any],
    current_username: str,
    incremental: dict[str, Any],
    markers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if incremental.get("mode") not in {"incremental", "unchanged"}:
        return []
    baseline = baseline_pointer(root)
    if baseline is None:
        return []
    _, plan = baseline
    target_marker = portable.digest(evidence.get("target"))[:16]
    preview = plan.get("publication_preview")
    if not isinstance(preview, dict):
        return []
    bodies = preview.get("body_files")
    if not isinstance(bodies, list):
        return []
    planned = {
        (item.get("publication_id"), item.get("revision"), item.get("kind")): item.get("sha256")
        for item in bodies
        if isinstance(item, dict)
    }
    action_values = preview.get("actions")
    if isinstance(action_values, list):
        planned_commands = {
            (item.get("publication_id"), item.get("revision"), item.get("kind")): item.get(
                "operation"
            )
            for item in action_values
            if isinstance(item, dict) and item.get("publication_id") is not None
        }
    else:
        planned_commands = {
            (item.get("publication_id"), item.get("revision"), item.get("kind")): item.get(
                "outcome"
            )
            for item in cast(list[object], preview.get("commands", []))
            if isinstance(item, dict)
        }
    finding_publications = {
        (item.get("finding_id"), item.get("revision")): item
        for item in cast(list[object], plan.get("finding_publications", []))
        if isinstance(item, dict)
    }
    previous_ledger = plan.get("publication_ledger")
    if not isinstance(previous_ledger, list):
        previous_ledger = []
    previous = {
        (item.get("id"), item.get("revision"), item.get("kind")): item
        for item in previous_ledger
        if isinstance(item, dict)
    }
    latest_previous_by_id: dict[str, dict[str, Any]] = {}
    for identity, item in previous.items():
        item_id, revision, _ = identity
        current = latest_previous_by_id.get(str(item_id))
        if current is None or isinstance(revision, int) and revision > current["revision"]:
            latest_previous_by_id[str(item_id)] = item
    issue_identities = {
        identity for identity in set(planned) | set(previous) if identity[2] == "issue"
    }
    project = evidence.get("project")
    if issue_identities and (
        not isinstance(project, dict)
        or not isinstance(project.get("id"), int)
        or not isinstance(project.get("hostname"), str)
    ):
        raise portable.WorkflowError("project identity is unavailable for issue marker lookup")
    if len(issue_identities) > 50:
        raise portable.WorkflowError("too many recommended issues for bounded marker lookup")
    project_value = cast(dict[str, Any], project)
    previous_issues: dict[str, dict[str, Any]] = {}
    for identity, item in previous.items():
        issue_id, revision, kind = identity
        current = previous_issues.get(str(issue_id))
        if kind == "issue" and (
            current is None or isinstance(revision, int) and revision > current["revision"]
        ):
            previous_issues[str(issue_id)] = item

    def issue_marker(value: dict[str, Any]) -> dict[str, Any] | None:
        if username(value.get("author")) != current_username:
            return None
        description = value.get("description")
        if not isinstance(description, str) or PUBLICATION_MARKER_PREFIX not in description:
            return None
        marker = publication_marker(description)
        if marker is None or marker["kind"] != "issue" or marker["target"] != target_marker:
            return None
        return {
            **marker,
            "note_id": value.get("iid"),
            "note_url": value.get("web_url"),
            "discussion_id": None,
            "author_username": current_username,
            "body_sha256": hashlib.sha256(description.encode()).hexdigest(),
            "resource_type": "issue",
            "is_root": True,
            "position": None,
            "root_note_id": None,
            "resource_title": value.get("title"),
            "resource_body": description,
        }

    for issue_id in sorted({str(identity[0]) for identity in issue_identities}):
        bound = previous_issues.get(issue_id)
        if bound is not None:
            value = portable.glab_json(
                cast(str, project_value["hostname"]),
                f"projects/{project_value['id']}/issues/{bound['note_id']}",
            )
            if not isinstance(value, dict):
                raise portable.WorkflowError("bound recommended issue is unavailable")
            marker = issue_marker(value)
            if marker is None or marker["id"] != issue_id:
                raise portable.WorkflowError("bound recommended issue marker changed")
            markers.append(marker)
            continue
        component = portable.paginated(
            cast(str, project_value["hostname"]),
            f"projects/{project_value['id']}/issues?scope=all&in=description&search={quote(issue_id, safe='')}",
        )
        if component.get("complete") is not True:
            raise portable.WorkflowError("recommended issue marker lookup is incomplete")
        for issue in cast(list[object], component.get("items", [])):
            if not isinstance(issue, dict):
                continue
            marker = issue_marker(issue)
            if marker is not None and marker["id"] == issue_id:
                markers.append(marker)
    trusted: list[dict[str, Any]] = []
    for marker in markers:
        if marker.get("target") != target_marker:
            continue
        identity = (marker.get("id"), marker.get("revision"), marker.get("kind"))
        prior = previous.get(identity)
        if prior is not None:
            if any(
                marker.get(key) != prior.get(key)
                for key in (
                    "note_id",
                    "note_url",
                    "discussion_id",
                    "author_username",
                    "body_sha256",
                    "resource_type",
                    "is_root",
                    "position",
                    "root_note_id",
                    "target",
                    "resource_title",
                    "resource_body",
                )
            ):
                raise portable.WorkflowError("trusted publication marker binding changed")
            trusted.append(marker)
            continue
        expected_body_digest = planned.get(identity)
        if expected_body_digest is None or marker.get("body_sha256") != expected_body_digest:
            continue
        outcome = planned_commands.get(identity)
        if marker["kind"] == "issue":
            binding_valid = marker.get("resource_type") == "issue"
        elif marker["kind"] == "thread":
            binding_valid = (
                marker.get("resource_type") == "note"
                and marker.get("is_root") is False
                and marker.get("discussion_id") is not None
                and str(marker.get("root_note_id")) == str(marker["id"])[len("thread-") :]
            )
        else:
            binding_valid = (
                marker.get("resource_type") == "note"
                and marker.get("discussion_id") is not None
                and marker.get("is_root") is (outcome in {"create_general", "create_line"})
            )
            prior_marker = latest_previous_by_id.get(str(marker["id"]))
            if binding_valid and outcome in {"reply", "resolve", "reopen"}:
                binding_valid = prior_marker is not None and marker.get(
                    "discussion_id"
                ) == prior_marker.get("discussion_id")
            spec = finding_publications.get((marker["id"], marker["revision"]))
            if binding_valid and outcome == "create_line" and spec is not None:
                position = marker.get("position")
                binding_valid = isinstance(position, dict) and (
                    position.get("new_path") == spec.get("path")
                    and position.get("new_line") == spec.get("line")
                    or position.get("old_path") == spec.get("path")
                    and position.get("old_line") == spec.get("old_line")
                )
        if binding_valid:
            trusted.append(marker)
    identities = [(item["id"], item["revision"], item["kind"]) for item in trusted]
    if len(identities) != len(set(identities)):
        raise portable.WorkflowError("a trusted publication marker appears more than once")
    return trusted


def artifact_for_digest(root: Path, kind: str, digest: object) -> tuple[Path, dict[str, Any]]:
    if not portable.is_digest(digest):
        raise portable.WorkflowError(f"baseline {kind} digest is invalid")
    path = root / "artifacts" / kind / f"{digest}.json"
    source = portable.regular_file(path, f"baseline {kind}")
    if source != path.resolve() or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise portable.WorkflowError(f"baseline {kind} content address changed")
    _, payload = portable.artifact_payload(source, kind)
    return source, payload


def rejected_candidate_is_affected(candidate: dict[str, Any], delta: dict[str, Any]) -> bool:
    return bool(
        set(cast(list[str], candidate.get("paths", [])))
        & set(cast(list[str], delta.get("changed_paths", [])))
        or set(cast(list[str], candidate.get("thread_ids", [])))
        & (
            set(cast(list[str], delta.get("changed_thread_ids", [])))
            | set(cast(list[str], delta.get("changed_note_ids", [])))
        )
        or set(cast(list[str], candidate.get("metadata_fields", [])))
        & set(cast(list[str], delta.get("metadata_fields", [])))
        or candidate.get("ci") is True
        and delta.get("pipelines_changed") is True
    )


def incremental_context(
    evidence: dict[str, Any], context: dict[str, Any], root: Path, requested: str
) -> dict[str, Any]:
    baseline_state_path = root / BASELINE_NAME
    baseline_state_digest = None
    baseline_state_error = None
    if baseline_state_path.exists() or baseline_state_path.is_symlink():
        try:
            baseline_state_digest = hashlib.sha256(
                portable.regular_file(
                    baseline_state_path, "code-review baseline state"
                ).read_bytes()
            ).hexdigest()
        except portable.WorkflowError as exc:
            baseline_state_error = str(exc)
    empty_delta: dict[str, Any] = {
        "from_head": None,
        "to_head": evidence.get("head_sha"),
        "changed_paths": [],
        "changed_thread_ids": [],
        "unchanged_thread_ids": [],
        "changed_note_ids": [],
        "unchanged_note_ids": [],
        "metadata_fields": [],
        "pipelines_changed": False,
    }
    empty = {
        "contract_version": INCREMENTAL_CONTRACT_VERSION,
        "requested": requested,
        "mode": "full",
        "reason": (
            "incremental review was explicitly disabled"
            if requested == "off"
            else "incremental review requires a full-review fallback"
            if baseline_state_error
            else "no compatible finalized baseline exists"
        ),
        "incremental_baseline": {
            "plan_path": None,
            "plan_digest": None,
            "state_digest": baseline_state_digest,
        },
        "previous_findings": [],
        "previous_finding_publications": [],
        "previous_recommended_issues": [],
        "previous_finding_ledger": [],
        "previous_publication_ledger": [],
        "previous_thread_decisions": [],
        "previous_rejected_candidates": [],
        "reconsidered_rejected_candidates": [],
        "incremental_delta": empty_delta,
        "incremental_delta_digest": portable.digest(empty_delta),
        "critic_required": False,
        "fallback_reasons": [baseline_state_error] if baseline_state_error else [],
    }
    if requested == "off" or baseline_state_error:
        return empty
    try:
        baseline = baseline_pointer(root)
        if baseline is None:
            return empty
        pointer, plan = baseline
        _, old_evidence = artifact_for_digest(
            root, "evidence_snapshot", plan.get("evidence_digest")
        )
        _, old_context = artifact_for_digest(root, "review_context", plan.get("context_digest"))
        failures: list[str] = []
        if plan.get("review_contract_version") != REVIEW_CONTRACT_VERSION:
            failures.append("baseline review contract predates runner-owned final reporting")
        if (
            old_context.get("evidence_digest") != plan.get("evidence_digest")
            or old_context.get("target") != plan.get("target")
            or old_evidence.get("target") != plan.get("target")
            or plan.get("target") != pointer.get("target")
        ):
            failures.append("baseline artifact bindings changed")
        if pointer.get("target") != evidence.get("target"):
            failures.append("target identity changed")
        if old_context.get("current_user_username") != context.get("current_user_username"):
            failures.append("current GitLab user changed")
        if old_context.get("role") != context.get("role"):
            failures.append("review role changed")
        if (
            old_evidence.get("retrieval_complete") is not True
            or old_context.get("complete") is not True
        ):
            failures.append("baseline evidence is incomplete")
        current_exact_git = context.get("exact_git")
        if (
            evidence.get("retrieval_complete") is not True
            or context.get("complete") is not True
            or not isinstance(current_exact_git, dict)
            or current_exact_git.get("complete") is not True
        ):
            failures.append("current evidence is incomplete")
        for key in ("base_sha", "start_sha"):
            if old_evidence.get(key) != evidence.get(key):
                failures.append(f"{key} changed")
        old_head = old_evidence.get("head_sha")
        current_head = evidence.get("head_sha")
        repo_root = Path(str(cast(dict[str, Any], context["exact_git"])["repo_root"]))
        if not isinstance(old_head, str) or not isinstance(current_head, str):
            failures.append("head SHA is unavailable")
        elif old_head != current_head:
            try:
                merge_base = str(
                    portable.git_read(repo_root, "merge-base", old_head, current_head)
                ).strip()
            except portable.WorkflowError:
                failures.append("head ancestry cannot be verified")
            else:
                if merge_base.lower() != old_head.lower():
                    failures.append("current head is not a descendant of the baseline head")
        if failures:
            return {
                **empty,
                "reason": "incremental review requires a full-review fallback",
                "fallback_reasons": failures,
            }
        changed_paths: list[str] = []
        if old_head != current_head:
            raw_paths = portable.git_read(
                repo_root,
                "diff",
                "--name-only",
                "--find-renames",
                "-z",
                cast(str, old_head),
                cast(str, current_head),
                "--",
                text=False,
            )
            if not isinstance(raw_paths, bytes):
                raise portable.WorkflowError("incremental changed paths are invalid")
            changed_paths = sorted(
                value
                for value in (item.decode(errors="replace") for item in raw_paths.split(b"\0"))
                if value
            )
        old_threads = {
            str(item.get("id")): item
            for item in cast(list[dict[str, Any]], old_context.get("discussions", []))
        }
        current_threads = {
            str(item.get("id")): item
            for item in cast(list[dict[str, Any]], context.get("discussions", []))
        }
        removed = sorted(set(old_threads) - set(current_threads))
        if removed:
            return {
                **empty,
                "reason": "incremental review requires a full-review fallback",
                "fallback_reasons": ["one or more baseline discussions disappeared"],
            }
        changed_threads = sorted(
            thread_id
            for thread_id, thread in current_threads.items()
            if thread_id not in old_threads
            or discussion_signature(old_threads[thread_id]) != discussion_signature(thread)
        )
        unchanged_threads = sorted(set(old_threads) & set(current_threads) - set(changed_threads))
        old_notes = {
            str(item.get("id")): item
            for item in cast(list[dict[str, Any]], old_context.get("notes", []))
            if item.get("system") is not True
        }
        current_notes = {
            str(item.get("id")): item
            for item in cast(list[dict[str, Any]], context.get("notes", []))
            if item.get("system") is not True
        }
        if set(old_notes) - set(current_notes):
            return {
                **empty,
                "reason": "incremental review requires a full-review fallback",
                "fallback_reasons": ["one or more baseline notes disappeared"],
            }
        changed_notes = sorted(
            note_id
            for note_id, note in current_notes.items()
            if note_id not in old_notes
            or json.dumps(old_notes[note_id], sort_keys=True, ensure_ascii=False)
            != json.dumps(note, sort_keys=True, ensure_ascii=False)
        )
        unchanged_notes = sorted(set(old_notes) & set(current_notes) - set(changed_notes))
        old_object = cast(dict[str, Any], old_evidence.get("object", {}))
        current_object = cast(dict[str, Any], evidence.get("object", {}))
        ignored_metadata = {
            "created_at",
            "updated_at",
            "diff_refs",
            "sha",
            "merge_commit_sha",
            "squash_commit_sha",
            "_links",
        }
        metadata_keys = sorted((set(old_object) | set(current_object)) - ignored_metadata)
        metadata_fields = [
            key for key in metadata_keys if old_object.get(key) != current_object.get(key)
        ]
        if old_evidence.get("labels") != evidence.get("labels"):
            metadata_fields.append("label_catalog")
            metadata_fields.sort()
        pipelines_changed = old_evidence.get("pipelines") != evidence.get("pipelines")
        changed = bool(
            changed_paths
            or changed_threads
            or changed_notes
            or metadata_fields
            or pipelines_changed
        )
        delta: dict[str, Any] = {
            "from_head": old_head,
            "to_head": current_head,
            "changed_paths": changed_paths,
            "changed_thread_ids": changed_threads,
            "unchanged_thread_ids": unchanged_threads,
            "changed_note_ids": changed_notes,
            "unchanged_note_ids": unchanged_notes,
            "metadata_fields": metadata_fields,
            "pipelines_changed": pipelines_changed,
        }
        finding_ledger = cast(list[dict[str, Any]], plan.get("finding_ledger", []))
        previous_findings = [
            cast(dict[str, Any], item["record"])["finding"]
            for item in finding_ledger
            if item.get("kind") == "finding"
        ]
        previous_finding_publications = [
            cast(dict[str, Any], item["record"])["publication"]
            for item in finding_ledger
            if item.get("kind") == "finding"
        ]
        previous_recommended_issues = [
            cast(dict[str, Any], item["record"])["issue"]
            for item in finding_ledger
            if item.get("kind") == "issue"
        ]
        rejected_candidates = cast(list[dict[str, Any]], plan.get("rejected_candidate_ledger", []))
        return {
            **empty,
            "mode": "incremental" if changed else "unchanged",
            "reason": "compatible finalized baseline and changed MR evidence"
            if changed
            else "the MR has not changed since the finalized baseline",
            "incremental_baseline": {
                "plan_path": pointer["plan_path"],
                "plan_digest": pointer["plan_digest"],
                "state_digest": baseline_state_digest,
            },
            "previous_findings": previous_findings,
            "previous_finding_publications": previous_finding_publications,
            "previous_recommended_issues": previous_recommended_issues,
            "previous_finding_ledger": finding_ledger,
            "previous_publication_ledger": plan.get("publication_ledger", []),
            "previous_thread_decisions": plan.get("thread_decisions", []),
            "previous_rejected_candidates": rejected_candidates,
            "reconsidered_rejected_candidates": [
                item for item in rejected_candidates if rejected_candidate_is_affected(item, delta)
            ],
            "incremental_delta": delta,
            "incremental_delta_digest": portable.digest(delta),
            "critic_required": changed,
        }
    except portable.WorkflowError as exc:
        return {
            **empty,
            "reason": "incremental review requires a full-review fallback",
            "fallback_reasons": [str(exc)],
        }


def annotate_discussion(value: dict[str, Any], web_url: str) -> dict[str, Any]:
    notes = value.get("notes")
    if not isinstance(notes, list) or not notes or not isinstance(notes[0], dict):
        raise portable.WorkflowError(f"discussion {value.get('id')!r} has no root note")
    root = cast(dict[str, Any], notes[0])
    note_id = root.get("id")
    stable_id(note_id)
    position = root.get("position") if isinstance(root.get("position"), dict) else None
    result = dict(value)
    result.update(
        {
            "root_note_id": note_id,
            "root_note_url": f"{web_url}#note_{note_id}",
            "root_author_username": username(root.get("author")),
            "root_resolved_by_username": username(root.get("resolved_by")),
            "root_resolvable": root.get("resolvable") is True,
            "root_resolved": root.get("resolved") is True,
            "root_system": root.get("system") is True,
            "root_position": position,
            "root_position_head_sha": position.get("head_sha") if position else None,
        }
    )
    return result


def server_changed_paths(evidence: dict[str, Any]) -> set[str]:
    changed = evidence.get("changed_files")
    if not isinstance(changed, dict) or changed.get("complete") is not True:
        raise portable.WorkflowError("GitLab changed-files evidence is incomplete")
    paths: set[str] = set()
    for value in cast(list[object], changed.get("items", [])):
        if not isinstance(value, dict):
            raise portable.WorkflowError("GitLab changed-files entry is invalid")
        path = value.get("new_path") or value.get("old_path")
        if not isinstance(path, str) or not path:
            raise portable.WorkflowError("GitLab changed-files entry has no path")
        paths.add(path)
    return paths


def exact_git_context(repo_root: str, evidence: dict[str, Any]) -> dict[str, Any]:
    root = repository_root(repo_root)
    errors: list[str] = []
    refs: dict[str, str] = {}
    for name in ("base_sha", "start_sha", "head_sha"):
        value = evidence.get(name)
        if not isinstance(value, str) or not value:
            errors.append(f"{name} is unavailable")
            continue
        try:
            resolved = str(
                portable.git_read(root, "rev-parse", "--verify", f"{value}^{{commit}}")
            ).strip()
        except portable.WorkflowError:
            errors.append(f"{name} is unavailable in the local repository")
            continue
        if resolved.lower() != value.lower():
            errors.append(f"{name} does not resolve exactly")
            continue
        refs[name] = resolved
    if set(refs) != {"base_sha", "start_sha", "head_sha"}:
        return {
            "repo_root": str(root),
            "refs": refs,
            "changed_paths": [],
            "diff_sha256": None,
            "complete": False,
            "errors": errors,
        }
    merge_base = str(
        portable.git_read(root, "merge-base", refs["start_sha"], refs["head_sha"])
    ).strip()
    if merge_base.lower() != refs["base_sha"].lower():
        errors.append("local merge-base does not match evidence base_sha")
    raw_paths = portable.git_read(
        root,
        "diff",
        "--name-only",
        "--find-renames",
        "-z",
        refs["base_sha"],
        refs["head_sha"],
        "--",
        text=False,
    )
    if not isinstance(raw_paths, bytes):
        raise portable.WorkflowError("local changed paths are invalid")
    changed_paths = sorted(
        value
        for value in (item.decode(errors="replace") for item in raw_paths.split(b"\0"))
        if value
    )
    try:
        expected_paths = server_changed_paths(evidence)
        if set(changed_paths) != expected_paths:
            errors.append("local changed paths do not match GitLab evidence")
    except portable.WorkflowError as exc:
        errors.append(str(exc))
    diff = portable.git_read(
        root,
        "diff",
        "--binary",
        "--find-renames",
        refs["base_sha"],
        refs["head_sha"],
        "--",
        text=False,
    )
    if not isinstance(diff, bytes):
        raise portable.WorkflowError("local exact diff is invalid")
    if len(diff) > portable.MAX_BYTES:
        errors.append("local exact diff exceeds the size limit")
        diff_digest = None
    else:
        diff_digest = hashlib.sha256(diff).hexdigest()
    return {
        "repo_root": str(root),
        "refs": refs,
        "changed_paths": changed_paths,
        "diff_sha256": diff_digest,
        "complete": not errors,
        "errors": errors,
    }


def collect_context(
    evidence: dict[str, Any], evidence_digest: str, repo_root: str, incremental: str = "auto"
) -> dict[str, Any]:
    if incremental not in {"auto", "off"}:
        raise portable.WorkflowError("incremental selection must be auto or off")
    project = evidence.get("project")
    target = evidence.get("target")
    object_value = evidence.get("object")
    discussions_component = evidence.get("discussions")
    if (
        not isinstance(project, dict)
        or not isinstance(project.get("id"), int)
        or not isinstance(project.get("hostname"), str)
        or not isinstance(target, dict)
        or not isinstance(object_value, dict)
        or not isinstance(discussions_component, dict)
    ):
        raise portable.WorkflowError("review evidence identity is incomplete")
    author_username = username(object_value.get("author"))
    web_url = object_value.get("web_url") or target.get("url")
    if not author_username or not isinstance(web_url, str) or not web_url:
        raise portable.WorkflowError("MR author or web URL is unavailable")
    current_user = portable.glab_json(project["hostname"], "user")
    current_username = username(current_user)
    current_user_id = current_user.get("id") if isinstance(current_user, dict) else None
    if (
        not current_username
        or not isinstance(current_user_id, int)
        or isinstance(current_user_id, bool)
        or current_user_id < 1
    ):
        raise portable.WorkflowError("current GitLab identity is unavailable")
    role = "author" if current_username == author_username else "reviewer"
    notes_component = portable.paginated(
        project["hostname"],
        f"projects/{project['id']}/merge_requests/{target['iid']}/notes?sort=asc",
    )
    errors = [portable.redact(value) for value in cast(list[str], notes_component["errors"])]
    if discussions_component.get("complete") is not True:
        errors.extend(
            portable.redact(value)
            for value in cast(list[str], discussions_component.get("errors", []))
        )
    try:
        discussions = [
            annotate_discussion(value, web_url)
            for value in deduplicate(
                cast(list[object], discussions_component.get("items", [])), "discussion"
            )
        ]
        nested_notes = [
            note
            for discussion in discussions
            for note in cast(list[object], discussion.get("notes", []))
        ]
        notes = deduplicate([*nested_notes, *cast(list[object], notes_component["items"])], "note")
        notes = [{**note, "note_url": f"{web_url}#note_{note['id']}"} for note in notes]
    except portable.WorkflowError as exc:
        errors.append(str(exc))
        discussions, notes = [], []
    exact_git = exact_git_context(repo_root, evidence)
    errors.extend(cast(list[str], exact_git["errors"]))
    content_notes = [note for note in notes if note.get("system") is not True]
    system_notes = [note for note in notes if note.get("system") is True]
    publication_markers, marker_errors = collect_publication_markers(
        discussions, notes, current_username
    )
    errors.extend(marker_errors)
    counts = {
        "discussions": len(discussions),
        "notes": len(notes),
        "content_notes": len(content_notes),
        "system_notes": len(system_notes),
        "open_resolvable": sum(
            item["root_resolvable"] is True and item["root_resolved"] is False
            for item in discussions
            if item["root_system"] is False
        ),
        "resolved_resolvable": sum(
            item["root_resolvable"] is True and item["root_resolved"] is True
            for item in discussions
            if item["root_system"] is False
        ),
        "plain_discussions": sum(
            item["root_resolvable"] is False for item in discussions if item["root_system"] is False
        ),
    }
    result = {
        "schema_version": portable.ARTIFACT_VERSION,
        "profile": "code-review",
        "external_mutations": False,
        "evidence_digest": evidence_digest,
        "target": target,
        "role": role,
        "current_user_id": current_user_id,
        "current_user_username": current_username,
        "mr_author_username": author_username,
        "discussions": discussions,
        "notes": notes,
        "publication_markers": publication_markers,
        "counts": counts,
        "exact_git": exact_git,
        "complete": evidence.get("retrieval_complete") is True
        and notes_component["complete"] is True
        and not errors,
        "errors": errors,
        "artifact_root": evidence["artifact_root"],
        "prepared_at": datetime.now(UTC).isoformat(),
    }
    root = portable.artifact_root(Path(str(evidence["artifact_root"])))
    selection = incremental_context(evidence, result, root, incremental)
    try:
        trusted_markers = trusted_publication_markers(
            root, evidence, current_username, selection, publication_markers
        )
    except portable.WorkflowError as exc:
        delta: dict[str, Any] = {
            "from_head": None,
            "to_head": evidence.get("head_sha"),
            "changed_paths": [],
            "changed_thread_ids": [],
            "unchanged_thread_ids": [],
            "changed_note_ids": [],
            "unchanged_note_ids": [],
            "metadata_fields": [],
            "pipelines_changed": False,
        }
        selection = {
            **selection,
            "mode": "full",
            "reason": "incremental review requires a full-review fallback",
            "incremental_baseline": {
                "plan_path": None,
                "plan_digest": None,
                "state_digest": selection["incremental_baseline"]["state_digest"],
            },
            "previous_findings": [],
            "previous_finding_publications": [],
            "previous_recommended_issues": [],
            "previous_finding_ledger": [],
            "previous_publication_ledger": [],
            "previous_thread_decisions": [],
            "previous_rejected_candidates": [],
            "reconsidered_rejected_candidates": [],
            "incremental_delta": delta,
            "incremental_delta_digest": portable.digest(delta),
            "critic_required": False,
            "fallback_reasons": [*selection["fallback_reasons"], str(exc)],
        }
        trusted_markers = []
    result["incremental"] = selection
    result["publication_markers"] = trusted_markers
    previous_marker_identities = {
        (item.get("id"), item.get("revision"), item.get("kind"))
        for item in cast(list[dict[str, Any]], selection.get("previous_publication_ledger", []))
    }
    new_issue_markers = [
        item
        for item in cast(list[dict[str, Any]], result["publication_markers"])
        if item["resource_type"] == "issue"
        and (item["id"], item["revision"], item["kind"]) not in previous_marker_identities
    ]
    if selection["mode"] == "unchanged" and new_issue_markers:
        selection["mode"] = "incremental"
        selection["reason"] = "a recommended issue publication was discovered"
        selection["critic_required"] = True
        selection["incremental_delta"]["changed_note_ids"].extend(
            f"issue:{item['note_id']}" for item in new_issue_markers
        )
        selection["incremental_delta"]["changed_note_ids"].sort()
        selection["incremental_delta_digest"] = portable.digest(selection["incremental_delta"])
    return result


def prepare_context(
    evidence_value: str,
    repo_root: str,
    incremental: str = "auto",
    review_mode: str = "normal",
    locale: str = "en",
) -> dict[str, object]:
    if review_mode not in {"fast", "normal", "deep"}:
        raise portable.WorkflowError("review mode must be fast, normal, or deep")
    if locale not in SUPPORTED_LOCALES:
        raise portable.WorkflowError("review locale must be en or ru")
    evidence_path, evidence, root, evidence_digest = evidence_context(evidence_value)
    current_evidence_path, _ = review_evidence_from_root(root)
    if current_evidence_path != evidence_path:
        raise portable.WorkflowError("review context requires the current evidence snapshot")
    context = collect_context(evidence, evidence_digest, repo_root, incremental)
    path, context_digest = portable.write_artifact(root, "review_context", context)
    incremental_value = cast(dict[str, Any], context["incremental"])
    delta = cast(dict[str, Any], incremental_value["incremental_delta"])
    selected_mode = (
        incremental_value["mode"]
        if incremental_value["mode"] in {"incremental", "unchanged"}
        else review_mode
    )
    critic_required = selected_mode in {"normal", "deep", "incremental"}
    exact_git = cast(dict[str, Any], context["exact_git"])
    resolved_repo = cast(str, exact_git["repo_root"])
    if context["complete"]:
        advance_progress(
            root,
            "context_ready",
            expected_stages={"prepared"},
            expected={"evidence_path": str(evidence_path), "evidence_digest": evidence_digest},
            repo_root=resolved_repo,
            context_path=str(path),
            context_digest=context_digest,
            mode=selected_mode,
            locale=locale,
            incremental=incremental,
            critic_receipt_path=None,
            critic_receipt_digest=None,
            finalize_report_path=None,
            finalize_report_digest=None,
            decision_path=None,
            decision_digest=None,
            plan_path=None,
            plan_digest=None,
        )
        if selected_mode == "unchanged":
            next_action = runner_action("report-review", "--artifact-root", str(root))
        elif critic_required:
            next_action = runner_action(
                "template-review", "--artifact-root", str(root), "--kind", "critic"
            )
        else:
            next_action = runner_action("finalize", "--artifact-root", str(root))
        stage = "context_ready"
    else:
        advance_progress(
            root,
            "prepared",
            expected_stages={"prepared"},
            expected={"evidence_path": str(evidence_path), "evidence_digest": evidence_digest},
            repo_root=resolved_repo,
            context_path=None,
            context_digest=None,
            mode=review_mode,
            locale=locale,
            incremental=incremental,
            critic_receipt_path=None,
            critic_receipt_digest=None,
            finalize_report_path=None,
            finalize_report_digest=None,
            decision_path=None,
            decision_digest=None,
            plan_path=None,
            plan_digest=None,
        )
        next_action = runner_action(
            "context",
            "--evidence",
            str(evidence_path),
            "--repo-root",
            resolved_repo,
            "--incremental",
            incremental,
            "--review-mode",
            review_mode,
            "--locale",
            locale,
        )
        stage = "prepared"
    return {
        "status": "ok" if context["complete"] else "incomplete",
        "summary": {
            "tldr": "Collected role, threads, notes, and exact local Git context.",
            "scope": [str(context["target"].get("url", ""))],
            "risks": [] if context["complete"] else context["errors"],
            "checks": ["current GitLab user", "thread completeness", "exact local SHAs"],
        },
        "artifact_path": str(path),
        "digest": context_digest,
        "role": context["role"],
        "counts": context["counts"],
        "incremental": {
            "mode": incremental_value["mode"],
            "reason": incremental_value["reason"],
            "critic_required": critic_required,
            "incremental_delta_digest": incremental_value["incremental_delta_digest"],
            "changed_paths": delta["changed_paths"],
            "changed_threads": len(delta["changed_thread_ids"]),
            "changed_notes": len(delta["changed_note_ids"]),
            "metadata_fields": delta["metadata_fields"],
            "pipelines_changed": delta["pipelines_changed"],
            "fallback_reasons": incremental_value["fallback_reasons"],
            "publication_plan_path": str(root / "review-publication.md")
            if incremental_value["mode"] == "unchanged"
            else None,
        },
        "review_mode": selected_mode,
        "locale": locale,
        "stage": stage,
        "next_action": next_action,
        "complete": context["complete"],
        "external_mutations": False,
    }


def validate_context_binding(
    context_value: str | Path, evidence_value: str | Path
) -> tuple[Path, dict[str, Any], str]:
    _, evidence, root, evidence_digest = evidence_context(evidence_value)
    path = portable.regular_file(Path(context_value), "review context")
    context_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = root / "artifacts" / "review_context" / f"{context_digest}.json"
    if path != expected:
        raise portable.WorkflowError("review context is not content-addressed")
    _, context = portable.artifact_payload(path, "review_context")
    if context.get("evidence_digest") != evidence_digest or context.get("target") != evidence.get(
        "target"
    ):
        raise portable.WorkflowError("review context does not bind the review evidence")
    return path, context, context_digest


def context_fingerprint(context: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in context.items() if key not in {"artifact_root", "prepared_at"}
    }


def contexts_match(expected: dict[str, Any], current: dict[str, Any]) -> bool:
    current_value = context_fingerprint(current)
    if "incremental" not in expected:
        current_value.pop("incremental", None)
        current_value.pop("publication_markers", None)
    return context_fingerprint(expected) == current_value


def refresh_context(context: dict[str, Any], evidence_value: str | Path) -> dict[str, Any]:
    _, evidence, _, evidence_digest = evidence_context(evidence_value)
    exact_git = context.get("exact_git")
    repo_root = exact_git.get("repo_root") if isinstance(exact_git, dict) else None
    if not isinstance(repo_root, str):
        raise portable.WorkflowError("review context repository root is unavailable")
    incremental = context.get("incremental")
    requested = incremental.get("requested") if isinstance(incremental, dict) else "auto"
    return collect_context(evidence, evidence_digest, repo_root, str(requested))


def content_addressed_artifact(
    value: str | Path, root: Path, kind: str
) -> tuple[Path, dict[str, Any], str]:
    path = portable.regular_file(Path(value), kind.replace("_", " "))
    artifact_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = root / "artifacts" / kind / f"{artifact_digest}.json"
    if path != expected:
        raise portable.WorkflowError(f"{kind.replace('_', ' ')} is not content-addressed")
    _, payload = portable.artifact_payload(path, kind)
    return path, payload, artifact_digest


def markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def metadata_assessment(evidence: dict[str, Any], assessment: object) -> dict[str, Any]:
    object_value = evidence.get("object")
    if not isinstance(object_value, dict):
        raise portable.WorkflowError("MR metadata is unavailable")
    title = object_value.get("title")
    description = object_value.get("description")
    labels = object_value.get("labels")
    state = object_value.get("state")
    if (
        not isinstance(title, str)
        or description is not None
        and not isinstance(description, str)
        or not isinstance(labels, list)
        or not all(isinstance(item, str) for item in labels)
        or not portable.nonempty_string(state)
    ):
        raise portable.WorkflowError("MR title, description, labels, or workflow state is invalid")
    result = {
        "observed": {
            "title": title,
            "description": description,
            "labels": labels,
            "workflow_state": state,
        },
        "assessment": assessment,
    }
    if not portable.mr_metadata_assessment_is_valid(result):
        raise portable.WorkflowError("MR metadata assessment is invalid")
    return result


def label_catalog(evidence: dict[str, Any]) -> list[dict[str, str | None]]:
    component = evidence.get("labels")
    if not isinstance(component, dict) or component.get("complete") is not True:
        raise portable.WorkflowError("project label catalog is incomplete")
    catalog: list[dict[str, str | None]] = []
    names: set[str] = set()
    folded: set[str] = set()
    for value in cast(list[object], component.get("items", [])):
        if not isinstance(value, dict) or not portable.nonempty_string(value.get("name")):
            raise portable.WorkflowError("project label catalog entry is invalid")
        name = cast(str, value["name"])
        description = value.get("description")
        if description is not None and not isinstance(description, str):
            raise portable.WorkflowError("project label description is invalid")
        if name in names or name.casefold() in folded:
            raise portable.WorkflowError("project label catalog contains duplicate names")
        names.add(name)
        folded.add(name.casefold())
        catalog.append({"name": name, "description": description})
    return sorted(catalog, key=lambda item: (cast(str, item["name"]).casefold(), item["name"]))


def validate_label_assessments(
    evidence: dict[str, Any], value: object, semver_impact: str
) -> dict[str, Any]:
    catalog = label_catalog(evidence)
    catalog_by_name = {cast(str, item["name"]): item for item in catalog}
    if not isinstance(value, list):
        raise portable.WorkflowError("label assessments must be an array")
    assessments: dict[str, dict[str, Any]] = {}
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"name", "status", "rationale"}
            or not portable.nonempty_string(item.get("name"))
            or item.get("status") not in {"applicable", "inapplicable", "unresolved"}
            or not portable.nonempty_string(item.get("rationale"))
            or item["name"] in assessments
        ):
            raise portable.WorkflowError("label assessment is invalid")
        assessments[cast(str, item["name"])] = cast(dict[str, Any], item)
    if set(assessments) != set(catalog_by_name):
        raise portable.WorkflowError("label assessments must cover the complete project catalog")

    compatibility: dict[str, list[str]] = {"major": [], "minor": [], "patch": []}
    for item in cast(list[dict[str, Any]], evidence["labels"]["items"]):
        semantics = portable.label_semantics(item)
        if semantics is not None and semantics[0] == "compatibility":
            compatibility[semantics[1]].append(cast(str, item["name"]))
    selected: str | None = None
    if semver_impact in compatibility:
        candidates = sorted(compatibility[semver_impact], key=str.casefold)
        if len(candidates) == 1:
            selected = candidates[0]
            if assessments[selected]["status"] != "applicable":
                raise portable.WorkflowError(
                    "SemVer impact requires the matching compatibility label"
                )
        elif len(candidates) > 1 and any(
            assessments[name]["status"] != "unresolved" for name in candidates
        ):
            raise portable.WorkflowError(
                "ambiguous SemVer compatibility labels must remain unresolved"
            )
        for impact, names in compatibility.items():
            if impact == semver_impact:
                continue
            if any(assessments[name]["status"] == "applicable" for name in names):
                raise portable.WorkflowError(
                    "an incompatible SemVer label cannot be assessed as applicable"
                )

    object_value = evidence.get("object")
    current_value = object_value.get("labels") if isinstance(object_value, dict) else None
    if not isinstance(current_value, list) or not all(
        isinstance(item, str) for item in current_value
    ):
        raise portable.WorkflowError("current MR labels are unavailable")
    current = sorted(set(cast(list[str], current_value)), key=str.casefold)
    if len(current) != len(current_value) or not set(current).issubset(catalog_by_name):
        raise portable.WorkflowError("current MR labels do not match the complete catalog")

    entries = [
        {
            **assessments[cast(str, item["name"])],
            "description": item["description"],
            "current": item["name"] in current,
        }
        for item in catalog
    ]
    add = sorted(
        [
            cast(str, item["name"])
            for item in entries
            if item["status"] == "applicable" and item["name"] not in current
        ],
        key=str.casefold,
    )
    remove = sorted(
        [
            cast(str, item["name"])
            for item in entries
            if item["status"] == "inapplicable" and item["name"] in current
        ],
        key=str.casefold,
    )
    proposed = sorted((set(current) - set(remove)) | set(add), key=str.casefold)
    return {
        "complete": True,
        "catalog_sha256": portable.digest(catalog),
        "catalog": catalog,
        "assessments": entries,
        "current": current,
        "add": add,
        "remove": remove,
        "proposed": proposed,
        "unresolved": [
            cast(str, item["name"]) for item in entries if item["status"] == "unresolved"
        ],
        "semver": {
            "impact": semver_impact,
            "candidates": sorted(compatibility.get(semver_impact, []), key=str.casefold),
            "selected": selected,
        },
    }


PRESENTATION_KEYS = {
    "title",
    "incremental_notice",
    "target_label",
    "role_label",
    "role_value",
    "verdict_label",
    "verdict_value",
    "metadata_heading",
    "labels_heading",
    "previous_findings_heading",
    "open_threads_heading",
    "closed_threads_heading",
    "local_fixes_heading",
    "new_findings_heading",
    "recommended_issues_heading",
    "checked_heading",
    "architecture_heading",
    "semver_heading",
    "checks_heading",
    "publication_heading",
    "no_items",
    "publication_warning",
    "previous_table_headers",
    "evidence_label",
    "relation_label",
    "severity_labels",
    "recovery_label",
}


def validate_presentation(value: object, incremental_mode: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != PRESENTATION_KEYS:
        raise portable.WorkflowError("review presentation is invalid")
    scalar_keys = PRESENTATION_KEYS - {
        "incremental_notice",
        "previous_table_headers",
        "severity_labels",
    }
    if not all(portable.nonempty_string(value.get(key)) for key in scalar_keys):
        raise portable.WorkflowError("review presentation labels must be non-empty")
    notice = value.get("incremental_notice")
    if incremental_mode == "incremental":
        if not portable.nonempty_string(notice):
            raise portable.WorkflowError("incremental review requires a localized notice")
    elif notice is not None:
        raise portable.WorkflowError("full review must not claim incremental review")
    headers = value.get("previous_table_headers")
    if (
        not isinstance(headers, list)
        or len(headers) != 5
        or not all(portable.nonempty_string(item) for item in headers)
    ):
        raise portable.WorkflowError("previous finding table headers are invalid")
    severity_labels = value.get("severity_labels")
    if (
        not isinstance(severity_labels, dict)
        or set(severity_labels) != {"critical", "high", "medium", "low"}
        or not all(portable.nonempty_string(item) for item in severity_labels.values())
    ):
        raise portable.WorkflowError("localized severity labels are invalid")
    return cast(dict[str, Any], value)


def validate_chat_assessment(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"necessity", "relevance", "change"}:
        raise portable.WorkflowError("review chat assessment is invalid")
    necessity = value.get("necessity")
    relevance = value.get("relevance")
    if (
        not isinstance(necessity, dict)
        or set(necessity) != {"status", "rationale"}
        or necessity.get("status") not in {"supported", "doubtful", "unconfirmed"}
        or not portable.nonempty_string(necessity.get("rationale"))
        or not isinstance(relevance, dict)
        or set(relevance) != {"status", "rationale"}
        or relevance.get("status") not in {"current", "partly_outdated", "outdated"}
        or not portable.nonempty_string(relevance.get("rationale"))
        or not portable.nonempty_string(value.get("change"))
    ):
        raise portable.WorkflowError("review chat assessment is invalid")
    return cast(dict[str, Any], value)


def suggestion_blocks(body: str) -> list[re.Match[str]]:
    matches = list(SUGGESTION_RE.finditer(body))
    if len(SUGGESTION_OPENER_RE.findall(body)) != len(matches):
        raise portable.WorkflowError("GitLab suggestion syntax is malformed")
    return matches


def validate_suggestion(
    body: str,
    *,
    repo_root: Path | None = None,
    head_sha: str | None = None,
    path: str | None = None,
    line: int | None = None,
) -> None:
    matches = suggestion_blocks(body)
    if len(matches) != 1:
        raise portable.WorkflowError("suggestion fix requires exactly one suggestion block")
    match = matches[0]
    before = int(match.group("before") or 0)
    after = int(match.group("after") or 0)
    if before > 100 or after > 100 or before + after + 1 > 201:
        raise portable.WorkflowError("GitLab suggestion range exceeds the supported limit")
    if repo_root is None or head_sha is None or path is None or line is None:
        return
    try:
        source = portable.git_read(repo_root, "show", f"{head_sha}:{path}")
    except portable.WorkflowError as exc:
        raise portable.WorkflowError("suggestion path is unavailable at the reviewed head") from exc
    line_count = len(str(source).splitlines())
    if line - before < 1 or line + after > line_count:
        raise portable.WorkflowError("GitLab suggestion range escapes the reviewed file")


def patch_paths(patch: str) -> list[str]:
    if (
        not patch.endswith("\n")
        or len(patch.encode()) > portable.MAX_BYTES
        or "\x00" in patch
        or "GIT binary patch" in patch
        or "Binary files " in patch
        or re.search(r"^index ", patch, re.MULTILINE)
        or re.search(
            r"^(?:old mode|new mode|new file mode|deleted file mode) (?:120000|160000)$",
            patch,
            re.MULTILINE,
        )
    ):
        raise portable.WorkflowError("Git patch is unsafe or exceeds the size limit")

    def tokens(value: str) -> list[str]:
        result: list[str] = []
        index = 0
        while index < len(value):
            while index < len(value) and value[index].isspace():
                index += 1
            if index == len(value):
                break
            if value[index] != '"':
                end = index
                while end < len(value) and not value[end].isspace():
                    end += 1
                result.append(value[index:end])
                index = end
                continue
            index += 1
            decoded = bytearray()
            while index < len(value) and value[index] != '"':
                if value[index] != "\\":
                    decoded.extend(value[index].encode())
                    index += 1
                    continue
                index += 1
                if index == len(value):
                    raise portable.WorkflowError("Git patch has an invalid quoted path")
                if value[index] in "01234567":
                    end = index
                    while end < min(index + 3, len(value)) and value[end] in "01234567":
                        end += 1
                    octet = int(value[index:end], 8)
                    if octet == 0 or octet > 0o377:
                        raise portable.WorkflowError("Git patch quoted path is unsafe")
                    decoded.append(octet)
                    index = end
                    continue
                escapes = {
                    "a": 7,
                    "b": 8,
                    "t": 9,
                    "n": 10,
                    "v": 11,
                    "f": 12,
                    "r": 13,
                    '"': 34,
                    "\\": 92,
                }
                if value[index] not in escapes:
                    raise portable.WorkflowError("Git patch has an invalid quoted path")
                decoded.append(escapes[value[index]])
                index += 1
            if index == len(value):
                raise portable.WorkflowError("Git patch has an unterminated quoted path")
            index += 1
            try:
                result.append(decoded.decode())
            except UnicodeDecodeError as exc:
                raise portable.WorkflowError("Git patch path is not UTF-8") from exc
        return result

    def relative_path(value: str, prefix: str) -> str:
        if not value.startswith(prefix):
            raise portable.WorkflowError("Git patch has an invalid file header")
        relative = PurePosixPath(value[len(prefix) :])
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise portable.WorkflowError("Git patch path escapes the repository")
        return relative.as_posix()

    paths: list[str] = []
    current: tuple[str, str] | None = None
    old_header: str | None = None
    new_header: str | None = None

    def finish_diff() -> None:
        if current is None:
            return
        if old_header is None or new_header is None:
            raise portable.WorkflowError("Git patch file headers are incomplete")
        old_path, new_path = current
        if old_header not in {"/dev/null", f"a/{old_path}"} or new_header not in {
            "/dev/null",
            f"b/{new_path}",
        }:
            raise portable.WorkflowError("Git patch file headers disagree")

    for raw_line in patch.splitlines():
        if raw_line.startswith(("rename from ", "rename to ", "copy from ", "copy to ")):
            raise portable.WorkflowError("Git patch renames and copies are unsupported")
        if raw_line.startswith(("--- ", "+++ ")):
            values = tokens(raw_line[4:])
            if (
                len(values) != 1
                or values[0] != "/dev/null"
                and not values[0].startswith("a/" if raw_line.startswith("--- ") else "b/")
            ):
                raise portable.WorkflowError("Git patch file path escapes the repository")
            if raw_line.startswith("--- "):
                old_header = values[0]
            else:
                new_header = values[0]
        if not raw_line.startswith("diff --git "):
            continue
        finish_diff()
        parts = tokens(raw_line[len("diff --git ") :])
        if len(parts) != 2:
            raise portable.WorkflowError("Git patch has an invalid diff header")
        old_path = relative_path(parts[0], "a/")
        new_path = relative_path(parts[1], "b/")
        if old_path != new_path:
            raise portable.WorkflowError("Git patch renames are unsupported")
        current = (old_path, new_path)
        old_header = None
        new_header = None
        paths.append(old_path)
    finish_diff()
    if not paths:
        raise portable.WorkflowError("Git patch contains no file diff")
    return sorted(set(paths))


def validate_git_patch(repo_root: Path, head_sha: str, patch: str) -> list[str]:
    paths = patch_paths(patch)
    for path in paths:
        tree_entry = str(portable.git_read(repo_root, "ls-tree", head_sha, "--", path)).strip()
        if tree_entry.startswith(("120000 ", "160000 ")):
            raise portable.WorkflowError("Git patch cannot modify symlinks or submodules")
    with tempfile.TemporaryDirectory(prefix="code-review-patch-") as temporary:
        environment = {**os.environ, "GIT_INDEX_FILE": str(Path(temporary) / "index")}
        try:
            read_tree = subprocess.run(
                ["git", "-C", str(repo_root), "read-tree", head_sha],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise portable.WorkflowError(
                "reviewed head cannot initialize Git patch validation"
            ) from exc
        if read_tree.returncode:
            raise portable.WorkflowError("reviewed head cannot initialize Git patch validation")
        apply_command = [
            "git",
            "-C",
            str(repo_root),
            "apply",
            "--cached",
            "--whitespace=nowarn",
            "-",
        ]
        try:
            checked = subprocess.run(
                [
                    *apply_command[:-1],
                    "--check",
                    "-",
                ],
                env=environment,
                input=patch.encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise portable.WorkflowError("Git patch validation could not be completed") from exc
        if checked.returncode:
            raise portable.WorkflowError("Git patch does not apply to the exact reviewed head")
        try:
            applied = subprocess.run(
                apply_command,
                env=environment,
                input=patch.encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise portable.WorkflowError("Git patch cannot be inspected safely") from exc
        if applied.returncode:
            raise portable.WorkflowError("Git patch cannot be inspected safely")
        try:
            inspected = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo_root),
                    "diff-index",
                    "--cached",
                    "--raw",
                    "-z",
                    head_sha,
                    "--",
                ],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise portable.WorkflowError("Git patch effective paths cannot be inspected") from exc
        if inspected.returncode:
            raise portable.WorkflowError("Git patch effective paths cannot be inspected")
    values = inspected.stdout.split(b"\0")
    effective_paths: list[str] = []
    index = 0
    while index < len(values) and values[index]:
        metadata = values[index].split()
        if len(metadata) != 5 or not metadata[0].startswith(b":"):
            raise portable.WorkflowError("Git patch effective diff is invalid")
        old_mode, new_mode, status = metadata[0][1:], metadata[1], metadata[4]
        if old_mode in {b"120000", b"160000"} or new_mode in {b"120000", b"160000"}:
            raise portable.WorkflowError("Git patch cannot modify symlinks or submodules")
        if status.startswith((b"R", b"C")):
            raise portable.WorkflowError("Git patch renames and copies are unsupported")
        index += 1
        if index >= len(values) or not values[index]:
            raise portable.WorkflowError("Git patch effective path is unavailable")
        try:
            effective_path = values[index].decode()
        except UnicodeDecodeError as exc:
            raise portable.WorkflowError("Git patch effective path is not UTF-8") from exc
        relative = PurePosixPath(effective_path)
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise portable.WorkflowError("Git patch effective path escapes the repository")
        effective_paths.append(relative.as_posix())
        index += 1
    if sorted(set(effective_paths)) != paths:
        raise portable.WorkflowError("Git patch declared and effective paths disagree")
    return paths


def changed_diff_lines(
    repo_root: Path, base_sha: str, head_sha: str, path: str
) -> tuple[set[int], set[int]]:
    diff = str(portable.git_read(repo_root, "diff", "--unified=0", base_sha, head_sha, "--", path))
    old_lines: set[int] = set()
    new_lines: set[int] = set()
    pattern = re.compile(
        r"^@@ -(?P<old>[0-9]+)(?:,(?P<old_count>[0-9]+))? "
        r"\+(?P<new>[0-9]+)(?:,(?P<new_count>[0-9]+))? @@",
        re.MULTILINE,
    )
    for match in pattern.finditer(diff):
        old_start = int(match.group("old"))
        new_start = int(match.group("new"))
        old_count = int(match.group("old_count") or 1)
        new_count = int(match.group("new_count") or 1)
        old_lines.update(range(old_start, old_start + old_count))
        new_lines.update(range(new_start, new_start + new_count))
    return old_lines, new_lines


def expected_thread_bindings(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    discussions = cast(list[dict[str, Any]], context.get("discussions", []))
    expected: dict[str, dict[str, Any]] = {}
    for item in discussions:
        if item.get("root_system") is True:
            continue
        meaningful = [
            note
            for note in cast(list[dict[str, Any]], item.get("notes", []))
            if note.get("system") is not True and isinstance(note.get("body"), str)
        ]
        if not meaningful:
            raise portable.WorkflowError("non-system discussion has no meaningful note")
        last_note = meaningful[-1]
        expected[str(item["root_note_id"])] = {
            **item,
            "state": "resolved"
            if item.get("root_resolved") is True
            else "open"
            if item.get("root_resolvable") is True
            else "plain",
            "url": item.get("root_note_url"),
            "last_note_id": last_note.get("id"),
            "last_note_body_sha256": hashlib.sha256(
                cast(str, last_note["body"]).encode()
            ).hexdigest(),
        }
    marked_root_note_ids = {
        str(item["note_id"])
        for item in cast(list[dict[str, Any]], context.get("publication_markers", []))
        if item.get("kind") == "finding"
        and item.get("resource_type") == "note"
        and item.get("is_root") is True
    }
    expected = {key: value for key, value in expected.items() if key not in marked_root_note_ids}
    discussion_note_ids = {
        str(note.get("id"))
        for discussion in discussions
        for note in cast(list[dict[str, Any]], discussion.get("notes", []))
    }
    for note in cast(list[dict[str, Any]], context.get("notes", [])):
        note_id = str(note.get("id"))
        if (
            note.get("system") is not True
            and note_id not in discussion_note_ids
            and note_id not in marked_root_note_ids
        ):
            body = note.get("body")
            if not isinstance(body, str):
                raise portable.WorkflowError("non-system note body is invalid")
            expected[note_id] = {
                "root_note_url": note.get("note_url"),
                "state": "plain",
                "url": note.get("note_url"),
                "last_note_id": note.get("id"),
                "last_note_body_sha256": hashlib.sha256(body.encode()).hexdigest(),
            }
    return expected


def validate_thread_fix(
    item: dict[str, Any],
    source: dict[str, Any],
    repo_root: Path,
    head_sha: str,
) -> None:
    fix_mode = item.get("fix_mode")
    if fix_mode not in {"suggestion", "patch", "not_required"}:
        raise portable.WorkflowError("thread fix mode is invalid")
    response = item.get("proposed_response")
    suggestion_count = len(suggestion_blocks(response)) if isinstance(response, str) else 0
    position = source.get("root_position")
    current_new_line = (
        isinstance(position, dict)
        and isinstance(position.get("new_path"), str)
        and isinstance(position.get("new_line"), int)
        and position.get("head_sha") == head_sha
    )
    if fix_mode == "suggestion" and (
        item.get("outcome") in {"no_publication", "local_fix"}
        or not current_new_line
        or suggestion_count != 1
        or item.get("patch") is not None
    ):
        raise portable.WorkflowError(
            "an applicable current-line thread fix requires exactly one suggestion block"
        )
    if fix_mode == "suggestion":
        exact_position = cast(dict[str, Any], position)
        validate_suggestion(
            cast(str, response),
            repo_root=repo_root,
            head_sha=head_sha,
            path=cast(str, exact_position["new_path"]),
            line=cast(int, exact_position["new_line"]),
        )
    if fix_mode == "patch" and (
        item.get("outcome") == "no_publication"
        or not portable.nonempty_string(item.get("patch"))
        or suggestion_count
    ):
        raise portable.WorkflowError("thread patch fix is invalid")
    if fix_mode == "patch":
        validate_git_patch(repo_root, head_sha, cast(str, item["patch"]))
    if fix_mode == "not_required" and (item.get("patch") is not None or suggestion_count):
        raise portable.WorkflowError(
            "a thread without a code fix cannot contain suggestion or patch"
        )
    if item.get("outcome") == "no_publication" and fix_mode != "not_required":
        raise portable.WorkflowError("a non-published thread cannot claim a code fix")
    if item.get("outcome") == "local_fix" and fix_mode != "patch":
        raise portable.WorkflowError("a local thread fix requires a Git patch")


def validate_finding_publications(value: object, finding_ids: set[str]) -> list[dict[str, Any]]:
    keys = {"finding_id", "type", "path", "line", "old_line", "body", "fix_mode", "patch"}
    if not isinstance(value, list):
        raise portable.WorkflowError("finding publications must be an array")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != keys:
            raise portable.WorkflowError("finding publication is invalid")
        finding_id = item.get("finding_id")
        publication_type = item.get("type")
        path, line, old_line = item.get("path"), item.get("line"), item.get("old_line")
        if (
            not portable.nonempty_string(finding_id)
            or finding_id not in finding_ids
            or finding_id in seen
            or publication_type not in {"general", "line", "local_fix"}
            or not portable.nonempty_string(item.get("body"))
            or item.get("fix_mode") not in {"suggestion", "patch"}
        ):
            raise portable.WorkflowError("finding publication identity or body is invalid")
        fix_mode = cast(str, item["fix_mode"])
        patch = item.get("patch")
        suggestion_count = len(suggestion_blocks(cast(str, item["body"])))
        if fix_mode == "patch":
            if not portable.nonempty_string(patch) or suggestion_count:
                raise portable.WorkflowError("patch fix requires a patch and forbids suggestion")
            patch_paths(cast(str, patch))
        elif patch is not None or suggestion_count != 1:
            raise portable.WorkflowError("suggestion fix requires one suggestion and no patch")
        if publication_type in {"general", "local_fix"}:
            if path is not None or line is not None or old_line is not None:
                raise portable.WorkflowError("non-line finding fix cannot have a line")
            if fix_mode != "patch":
                raise portable.WorkflowError("general and local finding fixes require a Git patch")
        elif (
            not portable.nonempty_string(path)
            or (line is None) == (old_line is None)
            or any(
                not isinstance(number, int) or isinstance(number, bool) or number < 1
                for number in (line, old_line)
                if number is not None
            )
        ):
            raise portable.WorkflowError("line finding publication position is invalid")
        elif old_line is not None and fix_mode != "patch":
            raise portable.WorkflowError("deleted-line finding fixes require a Git patch")
        elif fix_mode == "suggestion":
            validate_suggestion(cast(str, item["body"]))
        seen.add(cast(str, finding_id))
        result.append(cast(dict[str, Any], item))
    return result


def validate_previous_assessments(
    value: object, previous_findings: list[dict[str, Any]], previous_issues: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    keys = {
        "id",
        "kind",
        "status",
        "previous_status",
        "current_status",
        "rationale",
        "action",
        "publication_action",
        "publication_body",
        "critic_required",
    }
    if not isinstance(value, list):
        raise portable.WorkflowError("previous finding assessments must be an array")
    expected = {
        **{str(item.get("id")): "finding" for item in previous_findings},
        **{str(item.get("id")): "issue" for item in previous_issues},
    }
    actual: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict) or set(item) != keys:
            raise portable.WorkflowError("previous finding assessment is invalid")
        item_id = item.get("id")
        action = item.get("publication_action")
        body = item.get("publication_body")
        if (
            not portable.nonempty_string(item_id)
            or item_id in actual
            or item.get("kind") not in {"finding", "issue"}
            or item.get("status") not in PREVIOUS_FINDING_STATUSES
            or not isinstance(item.get("critic_required"), bool)
            or item.get("status") in {"changed", "unverified"}
            and item.get("critic_required") is not True
            or not all(
                portable.nonempty_string(item.get(key))
                for key in ("previous_status", "current_status", "rationale", "action")
            )
            or action not in {"no_publication", "reply", "resolve", "reopen", "update_issue"}
            or item.get("kind") == "issue"
            and action not in {"no_publication", "update_issue"}
            or item.get("kind") == "finding"
            and action == "update_issue"
            or action == "resolve"
            and item.get("status") not in {"fixed", "withdrawn"}
            or action == "reopen"
            and item.get("status") not in {"active", "changed", "unverified"}
            or (
                action == "no_publication"
                and body is not None
                or action != "no_publication"
                and not portable.nonempty_string(body)
            )
        ):
            raise portable.WorkflowError("previous finding assessment is invalid")
        actual[cast(str, item_id)] = cast(dict[str, Any], item)
    if set(actual) != set(expected) or any(
        actual[item_id]["kind"] != kind for item_id, kind in expected.items()
    ):
        raise portable.WorkflowError("every previous finding and issue requires one assessment")
    return list(actual.values())


def validate_recommended_issues(value: object) -> list[dict[str, Any]]:
    keys = {
        "id",
        "title",
        "problem",
        "risk",
        "evidence",
        "reason_out_of_scope",
        "minimum_fix",
        "body",
    }
    if not isinstance(value, list):
        raise portable.WorkflowError("recommended issues must be an array")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != keys:
            raise portable.WorkflowError("recommended issue is invalid")
        item_id = item.get("id")
        if (
            not portable.nonempty_string(item_id)
            or item_id in seen
            or not all(
                portable.nonempty_string(item.get(key))
                for key in (
                    "title",
                    "problem",
                    "risk",
                    "reason_out_of_scope",
                    "minimum_fix",
                    "body",
                )
            )
            or not isinstance(item.get("evidence"), list)
            or not item["evidence"]
            or not all(portable.nonempty_string(entry) for entry in item["evidence"])
        ):
            raise portable.WorkflowError("recommended issue content is invalid")
        seen.add(cast(str, item_id))
        result.append(cast(dict[str, Any], item))
    return result


def validate_rejected_candidates(value: object, decision: dict[str, Any]) -> list[dict[str, Any]]:
    keys = {
        "id",
        "source",
        "finding",
        "reason",
        "paths",
        "thread_ids",
        "metadata_fields",
        "ci",
    }
    if not isinstance(value, list):
        raise portable.WorkflowError("rejected candidates must be an array")
    primary = {
        str(item["id"]): item for item in cast(list[dict[str, Any]], decision.get("findings", []))
    }
    critic = {
        str(item["id"]): item
        for item in cast(list[dict[str, Any]], decision.get("critic_findings", []))
    }
    responses = {
        str(item["id"]): item for item in cast(list[dict[str, Any]], decision.get("responses", []))
    }
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != keys:
            raise portable.WorkflowError("rejected candidate is invalid")
        item_id = str(item.get("id"))
        source = item.get("source")
        expected = primary.get(item_id) if source == "primary" else critic.get(item_id)
        if (
            not portable.nonempty_string(item.get("id"))
            or item_id in seen
            or source not in {"primary", "critic"}
            or item.get("finding") != expected
            or not portable.nonempty_string(item.get("reason"))
            or responses.get(item_id, {}).get("decision") != "reject"
            or not all(
                isinstance(item.get(key), list)
                and all(isinstance(entry, str) for entry in item[key])
                for key in ("paths", "thread_ids", "metadata_fields")
            )
            or not isinstance(item.get("ci"), bool)
        ):
            raise portable.WorkflowError("rejected candidate is invalid")
        seen.add(item_id)
        result.append(cast(dict[str, Any], item))
    rejected_ids = {
        item_id
        for item_id in set(primary) | set(critic)
        if responses.get(item_id, {}).get("decision") == "reject"
    }
    if seen != rejected_ids:
        raise portable.WorkflowError("every rejected primary and critic candidate must be retained")
    return result


def validate_rejected_candidate_assessments(
    value: object, reconsidered: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise portable.WorkflowError("rejected candidate assessments must be an array")
    expected = {str(item["id"]) for item in reconsidered}
    actual: dict[str, dict[str, Any]] = {}
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"id", "decision", "reason"}
            or not portable.nonempty_string(item.get("id"))
            or item.get("decision") not in {"still_rejected", "promoted"}
            or not portable.nonempty_string(item.get("reason"))
            or item["id"] in actual
        ):
            raise portable.WorkflowError("rejected candidate assessment is invalid")
        actual[cast(str, item["id"])] = cast(dict[str, Any], item)
    if set(actual) != expected:
        raise portable.WorkflowError("every affected rejected candidate requires one assessment")
    return list(actual.values())


def previous_revisions(incremental: dict[str, Any]) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in cast(list[dict[str, Any]], incremental.get("previous_finding_ledger", [])):
        item_id, revision = item.get("id"), item.get("revision")
        if portable.nonempty_string(item_id) and isinstance(revision, int):
            result[cast(str, item_id)] = max(result.get(cast(str, item_id), 0), revision)
    for key in ("previous_finding_publications", "previous_recommended_issues"):
        for item in cast(list[dict[str, Any]], incremental.get(key, [])):
            item_id, revision = item.get("finding_id") or item.get("id"), item.get("revision")
            if portable.nonempty_string(item_id) and isinstance(revision, int):
                result[cast(str, item_id)] = max(result.get(cast(str, item_id), 0), revision)
    return result


def marker_index(context: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for marker in cast(list[dict[str, Any]], context.get("publication_markers", [])):
        marker_id = str(marker.get("id"))
        if marker_id not in result or marker.get("revision", 0) > result[marker_id].get(
            "revision", 0
        ):
            result[marker_id] = marker
    return result


def finding_revisions(
    incremental: dict[str, Any],
    assessments: list[dict[str, Any]],
    current_ids: set[str],
    markers: dict[str, dict[str, Any]],
) -> dict[str, int]:
    previous = previous_revisions(incremental)
    assessment_by_id = {item["id"]: item for item in assessments}
    revisions: dict[str, int] = {}
    for finding_id in current_ids:
        prior_revision = max(
            previous.get(finding_id, 0),
            int(markers[finding_id]["revision"]) if finding_id in markers else 0,
        )
        if prior_revision == 0:
            revisions[finding_id] = 1
            continue
        status = assessment_by_id[finding_id]["status"]
        revisions[finding_id] = prior_revision + (1 if status == "changed" else 0)
    return revisions


def publication_preflight(
    evidence: dict[str, Any], context: dict[str, Any], root: Path
) -> dict[str, str]:
    project = evidence.get("project")
    target = evidence.get("target")
    object_value = evidence.get("object")
    head_sha = evidence.get("head_sha")
    if (
        not isinstance(project, dict)
        or not isinstance(project.get("id"), int)
        or not portable.nonempty_string(project.get("hostname"))
        or not isinstance(target, dict)
        or not isinstance(target.get("iid"), int)
        or not isinstance(object_value, dict)
        or not portable.nonempty_string(object_value.get("state"))
        or not portable.is_sha(head_sha)
    ):
        raise portable.WorkflowError("MR identity is incomplete for publication preflight")
    hostname = cast(str, project["hostname"])
    state = cast(str, object_value["state"])
    endpoint = f"projects/{project['id']}/merge_requests/{target['iid']}"
    endpoint_argument = shlex.quote(endpoint)
    threads: dict[str, dict[str, Any]] = {}
    for discussion in cast(list[dict[str, Any]], context.get("discussions", [])):
        meaningful = [
            note
            for note in cast(list[dict[str, Any]], discussion.get("notes", []))
            if note.get("system") is not True and isinstance(note.get("body"), str)
        ]
        if meaningful:
            threads[str(discussion.get("id"))] = {
                "resolved": discussion.get("root_resolved") is True,
                "last_note_id": meaningful[-1].get("id"),
                "last_note_body": meaningful[-1]["body"],
            }
    issues = {
        str(marker["id"]): {
            "iid": marker["note_id"],
            "title": marker["resource_title"],
            "description": marker["resource_body"],
        }
        for marker in cast(list[dict[str, Any]], context.get("publication_markers", []))
        if marker.get("resource_type") == "issue"
    }
    payload = {
        "state": state,
        "diff_refs": {
            "base_sha": evidence.get("base_sha"),
            "start_sha": evidence.get("start_sha"),
            "head_sha": head_sha,
        },
        "threads": threads,
        "issues": issues,
    }
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    digest = hashlib.sha256(content.encode()).hexdigest()
    directory = portable.private_directory(root / "artifacts" / "review_plan" / "preflight")
    path, actual_digest = portable.write_companion(directory / f"{digest}.json", content)
    integrity = (
        f"printf '%s  %s\\n' {shlex.quote(actual_digest)} {shlex.quote(str(path))} "
        "| sha256sum --check --status"
    )
    query = shlex.quote(
        ".state == $expected[0].state and "
        ".diff_refs.base_sha == $expected[0].diff_refs.base_sha and "
        ".diff_refs.start_sha == $expected[0].diff_refs.start_sha and "
        ".diff_refs.head_sha == $expected[0].diff_refs.head_sha"
    )
    command = (
        f"{integrity} && glab api --hostname {shlex.quote(hostname)} --method GET "
        f"{endpoint_argument} | jq -e --slurpfile expected {shlex.quote(str(path))} {query}"
    )
    return {
        "path": str(path),
        "sha256": actual_digest,
        "command": command,
        "endpoint": endpoint,
        "hostname": hostname,
        "state": state,
    }


def publication_preview(
    evidence: dict[str, Any],
    context: dict[str, Any],
    root: Path,
    findings: list[dict[str, Any]],
    finding_specs: list[dict[str, Any]],
    assessments: list[dict[str, Any]],
    thread_decisions: list[dict[str, Any]],
    recommended_issues: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    project = cast(dict[str, Any], evidence["project"])
    target = cast(dict[str, Any], evidence["target"])
    preflight = publication_preflight(evidence, context, root)
    target_marker = portable.digest(context["target"])[:16]
    endpoint = preflight["endpoint"]
    hostname = preflight["hostname"]
    body_directory = portable.private_directory(root / "artifacts" / "review_plan" / "bodies")
    body_files: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    markers = marker_index(context)
    discussion_by_id = {
        str(item.get("id")): item
        for item in cast(list[dict[str, Any]], context.get("discussions", []))
    }
    incremental = cast(dict[str, Any], context["incremental"])
    previous = previous_revisions(incremental)
    assessment_by_id = {item["id"]: item for item in assessments}
    finding_ids = {str(item["id"]) for item in findings}
    revisions = finding_revisions(incremental, assessments, finding_ids, markers)
    previous_allowed = set(previous)

    def mr_note_absence_guard(marker: str) -> str:
        notes_endpoint = f"{endpoint}/notes?sort=asc&per_page=100"
        discussions_endpoint = f"{endpoint}/discussions?per_page=100"
        notes_query = shlex.quote('add | all(.[]; (((.body // "") | contains($marker)) | not))')
        discussions_query = shlex.quote(
            'add | all(.[]; all(.notes[]; (((.body // "") | contains($marker)) | not)))'
        )
        notes_guard = (
            f"glab api --hostname {shlex.quote(hostname)} --method GET --paginate "
            f"{shlex.quote(notes_endpoint)} | jq -s -e --arg marker {shlex.quote(marker)} "
            f"{notes_query}"
        )
        discussions_guard = (
            f"glab api --hostname {shlex.quote(hostname)} --method GET --paginate "
            f"{shlex.quote(discussions_endpoint)} | jq -s -e --arg marker "
            f"{shlex.quote(marker)} {discussions_query}"
        )
        return f"{notes_guard} && {discussions_guard}"

    def discussion_guard(
        discussion_endpoint: str,
        discussion_id: object,
        next_marker: str,
        previous_marker: str | None = None,
        *,
        next_must_exist: bool = False,
    ) -> str:
        predicates = [
            "((.notes[0].resolved // false) == $thread.resolved)",
        ]
        if next_must_exist:
            predicates.append(
                '(([.notes[] | select(.system != true)] | last | .body // "") | contains($next))'
            )
        else:
            predicates.extend(
                [
                    "(([.notes[] | select(.system != true)] | last | .id) == $thread.last_note_id)",
                    "(([.notes[] | select(.system != true)] | last | .body) == $thread.last_note_body)",
                    'all(.notes[]; (((.body // "") | contains($next)) | not))',
                ]
            )
        arguments = (
            f"--slurpfile expected {shlex.quote(preflight['path'])} "
            f"--arg discussion {shlex.quote(str(discussion_id))} "
            f"--arg next {shlex.quote(next_marker)}"
        )
        if previous_marker is not None:
            predicates.append('any(.notes[]; ((.body // "") | contains($previous)))')
            arguments += f" --arg previous {shlex.quote(previous_marker)}"
        query = "$expected[0].threads[$discussion] as $thread | " + " and ".join(predicates)
        return (
            f"glab api --hostname {shlex.quote(hostname)} --method GET "
            f"{shlex.quote(discussion_endpoint)} | jq -e {arguments} "
            f"{shlex.quote(query)}"
        )

    def issue_absence_guard(publication_id: str) -> str:
        issue_endpoint = (
            f"projects/{project['id']}/issues?scope=all&in=description&per_page=100"
            f"&search={quote(publication_id, safe='')}"
        )
        query = shlex.quote(
            'add | all(.[]; ((((.description // "") | contains($id)) and '
            '((.description // "") | contains($target))) | not))'
        )
        return (
            f"glab api --hostname {shlex.quote(hostname)} --method GET --paginate "
            f"{shlex.quote(issue_endpoint)} | jq -s -e "
            f"--arg id {shlex.quote(f'code-review:id={publication_id};')} "
            f"--arg target {shlex.quote(f'target={target_marker}')} {query}"
        )

    def issue_update_guard(marker: dict[str, Any], next_marker: str) -> str:
        issue_endpoint = f"projects/{project['id']}/issues/{marker['note_id']}"
        previous_marker = publication_marker_text(
            cast(str, marker["id"]), cast(int, marker["revision"]), "issue", target_marker
        )
        query = (
            ".title == $issue.title and .description == $issue.description and "
            '((.description // "") | contains($previous)) and '
            '((((.description // "") | contains($next)) | not))'
        )
        return (
            f"glab api --hostname {shlex.quote(hostname)} --method GET "
            f"{shlex.quote(issue_endpoint)} | jq -e "
            f"--slurpfile expected {shlex.quote(preflight['path'])} "
            f"--arg issue_id {shlex.quote(cast(str, marker['id']))} "
            f"--arg previous {shlex.quote(previous_marker)} "
            f"--arg next {shlex.quote(next_marker)} "
            f"{shlex.quote('$expected[0].issues[$issue_id] as $issue | ' + query)}"
        )

    enriched_findings: list[dict[str, Any]] = []
    spec_by_id = {str(item["finding_id"]): item for item in finding_specs}
    for finding in findings:
        finding_id = str(finding["id"])
        revision = revisions[finding_id]
        spec = spec_by_id.get(finding_id)
        if spec is None:
            enriched_findings.append(
                {
                    "finding_id": finding_id,
                    "revision": revision,
                    "type": "local_fix",
                    "path": None,
                    "line": None,
                    "old_line": None,
                    "body": finding["minimum_fix"],
                }
            )
            continue
        enriched = {**spec, "revision": revision}
        enriched_findings.append(enriched)
        marker = markers.get(finding_id) if finding_id in previous_allowed else None
        if marker is not None and marker.get("kind") != "finding":
            raise portable.WorkflowError("finding publication marker kind is invalid")
        assessment = assessment_by_id.get(finding_id)
        if marker is not None:
            if assessment is None:
                raise portable.WorkflowError("published baseline finding lacks an assessment")
            action = assessment.get("publication_action")
            if action == "no_publication":
                continue
            body = cast(str, assessment["publication_body"])
            next_revision = max(revision, cast(int, marker["revision"]) + 1)
            next_marker = publication_marker_text(
                finding_id, next_revision, "finding", target_marker
            )
            previous_marker = publication_marker_text(
                finding_id, cast(int, marker["revision"]), "finding", target_marker
            )
            recovery_command = None
            discussion_id = marker.get("discussion_id")
            if discussion_id is None:
                if action in {"resolve", "reopen"}:
                    raise portable.WorkflowError(
                        "a standalone marked note cannot be resolved or reopened"
                    )
                note_command = (
                    f"glab api --hostname {shlex.quote(hostname)} --method POST "
                    f"{shlex.quote(f'{endpoint}/notes')} -F body=@BODY_PATH"
                )
                action_guard = mr_note_absence_guard(next_marker)
            else:
                discussion_endpoint = f"{endpoint}/discussions/{discussion_id}"
                source_discussion = discussion_by_id.get(str(discussion_id))
                if source_discussion is None:
                    raise portable.WorkflowError("marked finding discussion is unavailable")
                if (
                    action in {"resolve", "reopen"}
                    and source_discussion.get("root_resolvable") is not True
                ):
                    raise portable.WorkflowError("finding discussion is not resolvable")
                if action == "resolve" and source_discussion.get("root_resolved") is True:
                    raise portable.WorkflowError("a resolved finding discussion cannot be resolved")
                if action == "reopen" and source_discussion.get("root_resolved") is not True:
                    raise portable.WorkflowError("an open finding discussion cannot be reopened")
                note_command = (
                    f"glab api --hostname {shlex.quote(hostname)} --method POST "
                    f"{shlex.quote(f'{discussion_endpoint}/notes')} -F body=@BODY_PATH"
                )
                action_guard = discussion_guard(
                    discussion_endpoint,
                    discussion_id,
                    next_marker,
                    previous_marker,
                )
                if action in {"resolve", "reopen"}:
                    resolved = "true" if action == "resolve" else "false"
                    note_command += (
                        f" && glab api --hostname {shlex.quote(hostname)} --method PUT "
                        f"{shlex.quote(discussion_endpoint)} -F resolved={resolved}"
                    )
                    recovery_command = (
                        f"{preflight['command']} && "
                        f"{discussion_guard(discussion_endpoint, discussion_id, next_marker, next_must_exist=True)} "
                        f"&& glab api --hostname {shlex.quote(hostname)} --method PUT "
                        f"{shlex.quote(discussion_endpoint)} -F resolved={resolved}"
                    )
            placeholder = "BODY_PATH"
            body = marked_body(body, finding_id, next_revision, "finding", target_marker)
            body_digest = hashlib.sha256(body.encode()).hexdigest()
            identity_digest = hashlib.sha256(finding_id.encode()).hexdigest()[:12]
            body_path, actual_digest = portable.write_companion(
                body_directory / f"{identity_digest}-{body_digest}.md", body
            )
            body_files.append(
                {
                    "publication_id": finding_id,
                    "revision": next_revision,
                    "kind": "finding",
                    "path": str(body_path),
                    "sha256": actual_digest,
                    "content": body,
                }
            )
            integrity = (
                f"printf '%s  %s\\n' {shlex.quote(actual_digest)} {shlex.quote(str(body_path))} "
                "| sha256sum --check --status"
            )
            commands.append(
                {
                    "publication_id": finding_id,
                    "revision": next_revision,
                    "kind": "finding",
                    "outcome": action,
                    "command": (
                        f"{preflight['command']} && {action_guard} && {integrity} && "
                        + note_command.replace(placeholder, shlex.quote(str(body_path)))
                    ),
                    "recovery_command": recovery_command,
                }
            )
            continue
        if context["role"] == "author":
            continue
        if spec["type"] == "general":
            command = (
                f"glab api --hostname {shlex.quote(hostname)} --method POST "
                f"{shlex.quote(f'{endpoint}/discussions')} -F body=@BODY_PATH"
            )
            outcome = "create_general"
        else:
            repository_url = str(context["target"].get("url", "")).split("/-/merge_requests/", 1)[0]
            line_option = "--line" if spec["line"] is not None else "--old-line"
            line_value = spec["line"] if spec["line"] is not None else spec["old_line"]
            command = (
                f"glab mr note create {target['iid']} --repo {shlex.quote(repository_url)} "
                f"--file {shlex.quote(cast(str, spec['path']))} {line_option} {line_value} < BODY_PATH"
            )
            outcome = "create_line"
        body = marked_body(cast(str, spec["body"]), finding_id, revision, "finding", target_marker)
        body_digest = hashlib.sha256(body.encode()).hexdigest()
        identity_digest = hashlib.sha256(finding_id.encode()).hexdigest()[:12]
        body_path, actual_digest = portable.write_companion(
            body_directory / f"{identity_digest}-{body_digest}.md", body
        )
        body_files.append(
            {
                "publication_id": finding_id,
                "revision": revision,
                "kind": "finding",
                "path": str(body_path),
                "sha256": actual_digest,
                "content": body,
            }
        )
        integrity = (
            f"printf '%s  %s\\n' {shlex.quote(actual_digest)} {shlex.quote(str(body_path))} "
            "| sha256sum --check --status"
        )
        commands.append(
            {
                "publication_id": finding_id,
                "revision": revision,
                "kind": "finding",
                "outcome": outcome,
                "command": (
                    f"{preflight['command']} && "
                    f"{mr_note_absence_guard(publication_marker_text(finding_id, revision, 'finding', target_marker))} "
                    f"&& {integrity} && "
                    + command.replace("BODY_PATH", shlex.quote(str(body_path)))
                ),
                "recovery_command": None,
            }
        )

    previous_issue_by_id = {
        str(item.get("id")): item
        for item in cast(list[dict[str, Any]], incremental.get("previous_recommended_issues", []))
    }
    enriched_issues: list[dict[str, Any]] = []
    for issue in recommended_issues:
        issue_id = str(issue["id"])
        prior = previous_issue_by_id.get(issue_id)
        assessment = assessment_by_id.get(issue_id)
        marker = markers.get(issue_id) if issue_id in previous_allowed else None
        previous_revision = max(
            int(prior["revision"]) if prior is not None else 0,
            int(marker["revision"]) if marker is not None else 0,
            previous.get(issue_id, 0),
        )
        revision = (
            1
            if previous_revision == 0
            else previous_revision + (1 if assessment and assessment["status"] == "changed" else 0)
        )
        enriched = {**issue, "revision": revision}
        enriched_issues.append(enriched)
        if marker is not None and marker.get("kind") != "issue":
            raise portable.WorkflowError("recommended issue marker kind is invalid")
        if marker is not None:
            if assessment is None:
                continue
            pending_update = previous.get(issue_id, 0) > int(marker["revision"])
            if (
                assessment["status"] == "changed"
                and assessment["publication_action"] != "update_issue"
                and not pending_update
            ):
                raise portable.WorkflowError("a changed published issue requires update_issue")
            if (
                assessment["status"] != "changed"
                and assessment["publication_action"] == "update_issue"
                and not pending_update
            ):
                raise portable.WorkflowError("an unchanged issue cannot be updated")
            if assessment["publication_action"] == "no_publication" and not pending_update:
                continue
            if assessment["publication_action"] != "update_issue" and not pending_update:
                raise portable.WorkflowError("published recommended issue requires update_issue")
        elif assessment is not None and assessment["publication_action"] == "update_issue":
            raise portable.WorkflowError("an unpublished recommended issue cannot be updated")
        body = marked_body(cast(str, issue["body"]), issue_id, revision, "issue", target_marker)
        body_digest = hashlib.sha256(body.encode()).hexdigest()
        identity_digest = hashlib.sha256(issue_id.encode()).hexdigest()[:12]
        body_path, actual_digest = portable.write_companion(
            body_directory / f"{identity_digest}-{body_digest}.md", body
        )
        body_files.append(
            {
                "publication_id": issue_id,
                "revision": revision,
                "kind": "issue",
                "path": str(body_path),
                "sha256": actual_digest,
                "content": body,
            }
        )
        integrity = (
            f"printf '%s  %s\\n' {shlex.quote(actual_digest)} {shlex.quote(str(body_path))} "
            "| sha256sum --check --status"
        )
        if marker is None:
            action_guard = issue_absence_guard(issue_id)
            issue_command = (
                f"glab api --hostname {shlex.quote(hostname)} --method POST "
                f"{shlex.quote(f'projects/{project["id"]}/issues')} "
                f"-F {shlex.quote(f'title={issue["title"]}')} "
                f"-F {shlex.quote(f'description=@{body_path}')}"
            )
            outcome = "create_issue"
        else:
            next_marker = publication_marker_text(issue_id, revision, "issue", target_marker)
            action_guard = issue_update_guard(marker, next_marker)
            issue_command = (
                f"glab api --hostname {shlex.quote(hostname)} --method PUT "
                f"{shlex.quote(f'projects/{project["id"]}/issues/{marker["note_id"]}')} "
                f"-F {shlex.quote(f'title={issue["title"]}')} "
                f"-F {shlex.quote(f'description=@{body_path}')}"
            )
            outcome = "update_issue"
        commands.append(
            {
                "publication_id": issue_id,
                "revision": revision,
                "kind": "issue",
                "outcome": outcome,
                "command": (
                    f"{preflight['command']} && {action_guard} && {integrity} && {issue_command}"
                ),
                "recovery_command": None,
            }
        )

    discussions = {
        str(item["root_note_id"]): item
        for item in cast(list[dict[str, Any]], context["discussions"])
        if item.get("root_system") is False
    }
    for assessment in assessments:
        assessment_id = str(assessment["id"])
        if assessment["kind"] != "finding" or assessment_id in finding_ids:
            continue
        marker = markers.get(assessment_id)
        action = assessment["publication_action"]
        if marker is None or action == "no_publication":
            continue
        if marker.get("kind") != "finding":
            raise portable.WorkflowError("previous finding marker kind is invalid")
        discussion_id = marker.get("discussion_id")
        if discussion_id is None and action in {"resolve", "reopen"}:
            raise portable.WorkflowError("a standalone finding cannot be resolved or reopened")
        revision = max(previous.get(assessment_id, 0), int(marker["revision"])) + 1
        body = marked_body(
            cast(str, assessment["publication_body"]),
            assessment_id,
            revision,
            "finding",
            target_marker,
        )
        body_digest = hashlib.sha256(body.encode()).hexdigest()
        identity_digest = hashlib.sha256(assessment_id.encode()).hexdigest()[:12]
        body_path, actual_digest = portable.write_companion(
            body_directory / f"{identity_digest}-{body_digest}.md", body
        )
        body_files.append(
            {
                "publication_id": assessment_id,
                "revision": revision,
                "kind": "finding",
                "path": str(body_path),
                "sha256": actual_digest,
                "content": body,
            }
        )
        integrity = (
            f"printf '%s  %s\\n' {shlex.quote(actual_digest)} {shlex.quote(str(body_path))} "
            "| sha256sum --check --status"
        )
        next_marker = publication_marker_text(assessment_id, revision, "finding", target_marker)
        previous_marker = publication_marker_text(
            assessment_id, int(marker["revision"]), "finding", target_marker
        )
        recovery_command = None
        if discussion_id is None:
            publish_command = (
                f"glab api --hostname {shlex.quote(hostname)} --method POST "
                f"{shlex.quote(f'{endpoint}/notes')} -F {shlex.quote(f'body=@{body_path}')}"
            )
            action_guard = mr_note_absence_guard(next_marker)
        else:
            discussion_endpoint = f"{endpoint}/discussions/{discussion_id}"
            source_discussion = discussion_by_id.get(str(discussion_id))
            if source_discussion is None:
                raise portable.WorkflowError("previous finding discussion is unavailable")
            if (
                action in {"resolve", "reopen"}
                and source_discussion.get("root_resolvable") is not True
            ):
                raise portable.WorkflowError("previous finding discussion is not resolvable")
            if action == "resolve" and source_discussion.get("root_resolved") is True:
                raise portable.WorkflowError("a resolved finding discussion cannot be resolved")
            if action == "reopen" and source_discussion.get("root_resolved") is not True:
                raise portable.WorkflowError("an open finding discussion cannot be reopened")
            publish_command = (
                f"glab api --hostname {shlex.quote(hostname)} --method POST "
                f"{shlex.quote(f'{discussion_endpoint}/notes')} "
                f"-F {shlex.quote(f'body=@{body_path}')}"
            )
            action_guard = discussion_guard(
                discussion_endpoint,
                discussion_id,
                next_marker,
                previous_marker,
            )
            if action in {"resolve", "reopen"}:
                resolved = "true" if action == "resolve" else "false"
                publish_command += (
                    f" && glab api --hostname {shlex.quote(hostname)} --method PUT "
                    f"{shlex.quote(discussion_endpoint)} -F resolved={resolved}"
                )
                recovery_command = (
                    f"{preflight['command']} && "
                    f"{discussion_guard(discussion_endpoint, discussion_id, next_marker, next_must_exist=True)} "
                    f"&& glab api --hostname {shlex.quote(hostname)} --method PUT "
                    f"{shlex.quote(discussion_endpoint)} -F resolved={resolved}"
                )
        commands.append(
            {
                "publication_id": assessment_id,
                "revision": revision,
                "kind": "finding",
                "outcome": action,
                "command": (
                    f"{preflight['command']} && {action_guard} && {integrity} && {publish_command}"
                ),
                "recovery_command": recovery_command,
            }
        )

    for decision in thread_decisions:
        action = decision["outcome"]
        if action in {"no_publication", "local_fix"}:
            continue
        root_note_id = str(decision["id"])
        publication_id = f"thread-{root_note_id}"
        marker = markers.get(publication_id)
        if marker is not None and marker.get("kind") != "thread":
            raise portable.WorkflowError("thread publication marker kind is invalid")
        revision = (int(marker["revision"]) if marker is not None else 0) + 1
        body = marked_body(
            cast(str, decision["proposed_response"]),
            publication_id,
            revision,
            "thread",
            target_marker,
        )
        body_digest = hashlib.sha256(body.encode()).hexdigest()
        identity_digest = hashlib.sha256(publication_id.encode()).hexdigest()[:12]
        body_path, actual_digest = portable.write_companion(
            body_directory / f"{identity_digest}-{body_digest}.md", body
        )
        body_files.append(
            {
                "publication_id": publication_id,
                "revision": revision,
                "kind": "thread",
                "path": str(body_path),
                "sha256": actual_digest,
                "content": body,
            }
        )
        integrity = (
            f"printf '%s  %s\\n' {shlex.quote(actual_digest)} {shlex.quote(str(body_path))} "
            "| sha256sum --check --status"
        )
        next_marker = publication_marker_text(publication_id, revision, "thread", target_marker)
        recovery_command = None
        discussion = discussions.get(root_note_id)
        if discussion is None:
            if action in {"resolve", "reopen"}:
                raise portable.WorkflowError("a plain note cannot be resolved or reopened")
            publish_command = (
                f"glab api --hostname {shlex.quote(hostname)} --method POST "
                f"{shlex.quote(f'{endpoint}/notes')} -F {shlex.quote(f'body=@{body_path}')}"
            )
            action_guard = mr_note_absence_guard(next_marker)
        else:
            discussion_endpoint = f"{endpoint}/discussions/{discussion['id']}"
            thread_previous_marker = (
                publication_marker_text(
                    publication_id, int(marker["revision"]), "thread", target_marker
                )
                if marker is not None
                else None
            )
            action_guard = discussion_guard(
                discussion_endpoint,
                discussion["id"],
                next_marker,
                thread_previous_marker,
            )
            publish_command = (
                f"glab api --hostname {shlex.quote(hostname)} --method POST "
                f"{shlex.quote(f'{discussion_endpoint}/notes')} "
                f"-F {shlex.quote(f'body=@{body_path}')}"
            )
            if action in {"resolve", "reopen"}:
                resolved = "true" if action == "resolve" else "false"
                publish_command += (
                    f" && glab api --hostname {shlex.quote(hostname)} --method PUT "
                    f"{shlex.quote(discussion_endpoint)} -F resolved={resolved}"
                )
                recovery_command = (
                    f"{preflight['command']} && "
                    f"{discussion_guard(discussion_endpoint, discussion['id'], next_marker, next_must_exist=True)} "
                    f"&& glab api --hostname {shlex.quote(hostname)} --method PUT "
                    f"{shlex.quote(discussion_endpoint)} -F resolved={resolved}"
                )
        commands.append(
            {
                "publication_id": publication_id,
                "revision": revision,
                "kind": "thread",
                "outcome": action,
                "command": (
                    f"{preflight['command']} && {action_guard} && {integrity} && {publish_command}"
                ),
                "recovery_command": recovery_command,
            }
        )

    result = {
        "mr_state": preflight["state"],
        "warning": "manual publication preview; no command was executed",
        "preflight_path": preflight["path"],
        "preflight_sha256": preflight["sha256"],
        "preflight_command": preflight["command"],
        "body_files": body_files,
        "commands": commands,
    }
    if not portable.review_publication_preview_is_valid(result):
        raise portable.WorkflowError("review publication preview is invalid")
    return result, enriched_findings, enriched_issues


def structured_publication_preflight(
    evidence: dict[str, Any], context: dict[str, Any], root: Path, labels: dict[str, Any]
) -> dict[str, str]:
    project = evidence.get("project")
    target = evidence.get("target")
    object_value = evidence.get("object")
    if (
        not isinstance(project, dict)
        or not isinstance(project.get("id"), int)
        or not portable.nonempty_string(project.get("hostname"))
        or not portable.nonempty_string(project.get("path"))
        or not isinstance(target, dict)
        or not isinstance(target.get("iid"), int)
        or not isinstance(object_value, dict)
        or not portable.nonempty_string(object_value.get("state"))
        or not portable.nonempty_string(object_value.get("web_url"))
        or not isinstance(object_value.get("diff_refs"), dict)
    ):
        raise portable.WorkflowError("MR identity is incomplete for publication preflight")
    refs = cast(dict[str, Any], object_value["diff_refs"])
    if any(not portable.is_sha(refs.get(key)) for key in ("base_sha", "start_sha", "head_sha")):
        raise portable.WorkflowError("MR refs are incomplete for publication preflight")
    payload = {
        "schema": "code-review/publication-preflight/v1",
        "actor": {
            "id": context["current_user_id"],
            "username": context["current_user_username"],
        },
        "target": {
            "hostname": project["hostname"],
            "project_id": project["id"],
            "project_path": project["path"],
            "mr_iid": target["iid"],
            "mr_url": object_value["web_url"],
        },
        "mr": {
            "state": object_value["state"],
            "diff_refs": {key: refs[key] for key in ("base_sha", "start_sha", "head_sha")},
        },
        "labels": {
            "catalog_sha256": labels["catalog_sha256"],
            "catalog": labels["catalog"],
            "current": labels["current"],
            "proposed": labels["proposed"],
        },
    }
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    digest = hashlib.sha256(content.encode()).hexdigest()
    directory = portable.private_directory(root / "artifacts" / "review_plan" / "preflight")
    path, actual_digest = portable.write_companion(directory / f"{digest}.json", content)
    return {"path": str(path), "sha256": actual_digest}


def structured_publication_preview(
    evidence: dict[str, Any],
    context: dict[str, Any],
    root: Path,
    findings: list[dict[str, Any]],
    finding_specs: list[dict[str, Any]],
    assessments: list[dict[str, Any]],
    thread_decisions: list[dict[str, Any]],
    recommended_issues: list[dict[str, Any]],
    label_review: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    preflight = structured_publication_preflight(evidence, context, root, label_review)
    target_marker = portable.digest(context["target"])[:16]
    body_directory = portable.private_directory(root / "artifacts" / "review_plan" / "bodies")
    patch_directory = portable.private_directory(root / "artifacts" / "review_plan" / "patches")
    helper_path = Path(__file__).resolve().with_name("review_publish.py")
    baseline_path = root / BASELINE_NAME
    body_files: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    markers = marker_index(context)
    incremental = cast(dict[str, Any], context["incremental"])
    previous = previous_revisions(incremental)
    previous_allowed = set(previous)
    assessment_by_id = {str(item["id"]): item for item in assessments}
    finding_ids = {str(item["id"]) for item in findings}
    revisions = finding_revisions(incremental, assessments, finding_ids, markers)
    discussion_by_id = {
        str(item["id"]): item for item in cast(list[dict[str, Any]], context["discussions"])
    }
    discussion_by_root = {
        str(item["root_note_id"]): item
        for item in cast(list[dict[str, Any]], context["discussions"])
        if item.get("root_system") is False
    }
    note_by_id = {
        str(item["id"]): item
        for item in cast(list[dict[str, Any]], context["notes"])
        if item.get("system") is not True
    }

    def enrich_fix(owner_kind: str, owner_id: str, item: dict[str, Any]) -> dict[str, Any]:
        patch = item.get("patch")
        if item.get("fix_mode") != "patch":
            return {**item, "patch_path": None, "patch_sha256": None}
        if not isinstance(patch, str):
            raise portable.WorkflowError("patch fix content is unavailable")
        identity = hashlib.sha256(f"{owner_kind}:{owner_id}".encode()).hexdigest()[:12]
        patch_digest = hashlib.sha256(patch.encode()).hexdigest()
        patch_path, actual_digest = portable.write_companion(
            patch_directory / f"{identity}-{patch_digest}.patch", patch
        )
        return {**item, "patch_path": str(patch_path), "patch_sha256": actual_digest}

    def body_with_fix(body: str, fix: dict[str, Any]) -> str:
        if fix.get("fix_mode") != "patch":
            return body
        patch = cast(str, fix["patch"])
        return f"{body.rstrip()}\n\n```diff\n{patch.rstrip()}\n```"

    enriched_threads = [enrich_fix("thread", str(item["id"]), item) for item in thread_decisions]

    def thread_expectation(source: dict[str, Any]) -> dict[str, Any]:
        meaningful = [
            note
            for note in cast(list[dict[str, Any]], source.get("notes", []))
            if note.get("system") is not True and isinstance(note.get("body"), str)
        ]
        if not meaningful:
            raise portable.WorkflowError("publication thread has no meaningful note")
        latest = meaningful[-1]
        position = source.get("root_position")
        return {
            "discussion_id": source["id"],
            "root_note_id": source["root_note_id"],
            "resolvable": source.get("root_resolvable") is True,
            "resolved": source.get("root_resolved") is True,
            "last_note_id": latest.get("id"),
            "last_note_body_sha256": hashlib.sha256(cast(str, latest["body"]).encode()).hexdigest(),
            "path": position.get("new_path") or position.get("old_path")
            if isinstance(position, dict)
            else None,
            "line": position.get("new_line") or position.get("old_line")
            if isinstance(position, dict)
            else None,
        }

    def note_expectation(source: dict[str, Any]) -> dict[str, Any]:
        body = source.get("body")
        if not isinstance(body, str):
            raise portable.WorkflowError("publication note body is invalid")
        return {"note_id": source["id"], "body_sha256": hashlib.sha256(body.encode()).hexdigest()}

    def marker_expectation(marker: dict[str, Any] | None) -> dict[str, Any] | None:
        if marker is None:
            return None
        return {
            key: marker.get(key)
            for key in (
                "id",
                "revision",
                "kind",
                "note_id",
                "discussion_id",
                "author_username",
                "body_sha256",
                "resource_type",
                "root_note_id",
            )
        }

    def add_body_action(
        publication_id: str,
        revision: int,
        kind: str,
        operation: str,
        raw_body: str,
        *,
        mutation: dict[str, Any] | None = None,
        thread: dict[str, Any] | None = None,
        note: dict[str, Any] | None = None,
        prior_marker: dict[str, Any] | None = None,
        issue: dict[str, Any] | None = None,
    ) -> None:
        body = marked_body(raw_body, publication_id, revision, kind, target_marker)
        body_digest = hashlib.sha256(body.encode()).hexdigest()
        identity_digest = hashlib.sha256(publication_id.encode()).hexdigest()[:12]
        body_path, actual_digest = portable.write_companion(
            body_directory / f"{identity_digest}-{body_digest}.md", body
        )
        body_record = {
            "publication_id": publication_id,
            "revision": revision,
            "kind": kind,
            "path": str(body_path),
            "sha256": actual_digest,
            "content": body,
        }
        body_files.append(body_record)
        spec = {
            "schema": "code-review/publication-action/v1",
            "preflight_sha256": preflight["sha256"],
            "operation": operation,
            "publication": {"id": publication_id, "revision": revision, "kind": kind},
            "body": {"path": str(body_path), "sha256": actual_digest},
            "expected": {
                "thread": thread,
                "note": note,
                "prior_marker": marker_expectation(prior_marker),
                "issue": issue,
            },
            "mutation": mutation or {},
        }
        action_digest = portable.digest(spec)
        action_id = f"{kind}:{publication_id}:r{revision}:{operation}"
        command = (
            f"python3 {shlex.quote(str(helper_path))} apply "
            f"--plan {shlex.quote(str(baseline_path))} "
            f"--action {shlex.quote(action_id)} --confirm {action_digest}"
        )
        actions.append(
            {
                "id": action_id,
                "sha256": action_digest,
                "kind": kind,
                "publication_id": publication_id,
                "revision": revision,
                "operation": operation,
                "command": command,
                "spec": spec,
            }
        )

    enriched_findings: list[dict[str, Any]] = []
    spec_by_id = {
        str(item["finding_id"]): enrich_fix("finding", str(item["finding_id"]), item)
        for item in finding_specs
    }
    for finding in findings:
        finding_id = str(finding["id"])
        revision = revisions[finding_id]
        publication_spec = spec_by_id.get(finding_id)
        if publication_spec is None:
            raise portable.WorkflowError("every actionable finding requires a concrete fix")
        enriched = {**publication_spec, "revision": revision}
        enriched_findings.append(enriched)
        marker = markers.get(finding_id) if finding_id in previous_allowed else None
        if marker is not None and marker.get("kind") != "finding":
            raise portable.WorkflowError("finding publication marker kind is invalid")
        assessment = assessment_by_id.get(finding_id)
        if marker is not None:
            if assessment is None:
                raise portable.WorkflowError("published baseline finding lacks an assessment")
            operation = cast(str, assessment["publication_action"])
            if operation == "no_publication":
                continue
            next_revision = max(revision, cast(int, marker["revision"]) + 1)
            discussion = (
                discussion_by_id.get(str(marker["discussion_id"]))
                if marker.get("discussion_id") is not None
                else None
            )
            if operation in {"resolve", "reopen"} and discussion is None:
                raise portable.WorkflowError("a standalone finding cannot change thread state")
            source_note = note_by_id.get(str(marker["note_id"])) if discussion is None else None
            add_body_action(
                finding_id,
                next_revision,
                "finding",
                operation,
                body_with_fix(cast(str, assessment["publication_body"]), publication_spec),
                mutation={
                    "desired_resolved": True
                    if operation == "resolve"
                    else False
                    if operation == "reopen"
                    else None
                },
                thread=thread_expectation(discussion) if discussion is not None else None,
                note=note_expectation(source_note) if source_note is not None else None,
                prior_marker=marker,
            )
            continue
        if context["role"] == "author":
            continue
        operation = "create_general" if publication_spec["type"] == "general" else "create_line"
        add_body_action(
            finding_id,
            revision,
            "finding",
            operation,
            body_with_fix(cast(str, publication_spec["body"]), publication_spec),
            mutation={
                "path": publication_spec["path"],
                "line": publication_spec["line"],
                "old_line": publication_spec["old_line"],
            },
        )

    previous_issue_by_id = {
        str(item.get("id")): item
        for item in cast(list[dict[str, Any]], incremental.get("previous_recommended_issues", []))
    }
    enriched_issues: list[dict[str, Any]] = []
    for issue_value in recommended_issues:
        issue_id = str(issue_value["id"])
        prior = previous_issue_by_id.get(issue_id)
        assessment = assessment_by_id.get(issue_id)
        marker = markers.get(issue_id) if issue_id in previous_allowed else None
        previous_revision = max(
            int(prior["revision"]) if prior is not None else 0,
            int(marker["revision"]) if marker is not None else 0,
            previous.get(issue_id, 0),
        )
        revision = (
            1
            if previous_revision == 0
            else previous_revision + (1 if assessment and assessment["status"] == "changed" else 0)
        )
        enriched = {**issue_value, "revision": revision}
        enriched_issues.append(enriched)
        if marker is not None and marker.get("kind") != "issue":
            raise portable.WorkflowError("recommended issue marker kind is invalid")
        if marker is not None:
            if assessment is None:
                continue
            pending_update = previous.get(issue_id, 0) > int(marker["revision"])
            if assessment["publication_action"] == "no_publication" and not pending_update:
                continue
            if assessment["publication_action"] != "update_issue" and not pending_update:
                raise portable.WorkflowError("published recommended issue requires update_issue")
            operation = "update_issue"
            expected_issue = {
                "iid": marker["note_id"],
                "title_sha256": hashlib.sha256(
                    cast(str, marker["resource_title"]).encode()
                ).hexdigest(),
                "description_sha256": hashlib.sha256(
                    cast(str, marker["resource_body"]).encode()
                ).hexdigest(),
            }
        else:
            if assessment is not None and assessment["publication_action"] == "update_issue":
                raise portable.WorkflowError("an unpublished recommended issue cannot be updated")
            operation = "create_issue"
            expected_issue = None
        add_body_action(
            issue_id,
            revision,
            "issue",
            operation,
            cast(str, issue_value["body"]),
            mutation={"title": issue_value["title"]},
            prior_marker=marker,
            issue=expected_issue,
        )

    for assessment in assessments:
        assessment_id = str(assessment["id"])
        if assessment["kind"] != "finding" or assessment_id in finding_ids:
            continue
        marker = markers.get(assessment_id)
        operation = cast(str, assessment["publication_action"])
        if marker is None or operation == "no_publication":
            continue
        if marker.get("kind") != "finding":
            raise portable.WorkflowError("previous finding marker kind is invalid")
        discussion = (
            discussion_by_id.get(str(marker["discussion_id"]))
            if marker.get("discussion_id") is not None
            else None
        )
        if operation in {"resolve", "reopen"} and discussion is None:
            raise portable.WorkflowError("a standalone finding cannot change thread state")
        source_note = note_by_id.get(str(marker["note_id"])) if discussion is None else None
        revision = max(previous.get(assessment_id, 0), int(marker["revision"])) + 1
        add_body_action(
            assessment_id,
            revision,
            "finding",
            operation,
            cast(str, assessment["publication_body"]),
            mutation={
                "desired_resolved": True
                if operation == "resolve"
                else False
                if operation == "reopen"
                else None
            },
            thread=thread_expectation(discussion) if discussion is not None else None,
            note=note_expectation(source_note) if source_note is not None else None,
            prior_marker=marker,
        )

    for decision in enriched_threads:
        operation = cast(str, decision["outcome"])
        if operation in {"no_publication", "local_fix"}:
            continue
        root_note_id = str(decision["id"])
        publication_id = f"thread-{root_note_id}"
        marker = markers.get(publication_id)
        if marker is not None and marker.get("kind") != "thread":
            raise portable.WorkflowError("thread publication marker kind is invalid")
        revision = (int(marker["revision"]) if marker is not None else 0) + 1
        discussion = discussion_by_root.get(root_note_id)
        source_note = note_by_id.get(root_note_id) if discussion is None else None
        if operation in {"resolve", "reopen"} and discussion is None:
            raise portable.WorkflowError("a plain note cannot change thread state")
        add_body_action(
            publication_id,
            revision,
            "thread",
            operation,
            body_with_fix(cast(str, decision["proposed_response"]), decision),
            mutation={
                "desired_resolved": True
                if operation == "resolve"
                else False
                if operation == "reopen"
                else None
            },
            thread=thread_expectation(discussion) if discussion is not None else None,
            note=note_expectation(source_note) if source_note is not None else None,
            prior_marker=marker,
        )

    if label_review["add"] or label_review["remove"]:
        label_spec = {
            "schema": "code-review/publication-action/v1",
            "preflight_sha256": preflight["sha256"],
            "operation": "update_labels",
            "publication": None,
            "body": None,
            "expected": {
                "thread": None,
                "note": None,
                "prior_marker": None,
                "issue": None,
            },
            "mutation": {
                "add": label_review["add"],
                "remove": label_review["remove"],
                "proposed": label_review["proposed"],
            },
        }
        action_digest = portable.digest(label_spec)
        action_id = "labels:update"
        actions.append(
            {
                "id": action_id,
                "sha256": action_digest,
                "kind": "labels",
                "publication_id": None,
                "revision": None,
                "operation": "update_labels",
                "command": (
                    f"python3 {shlex.quote(str(helper_path))} apply "
                    f"--plan {shlex.quote(str(baseline_path))} "
                    f"--action {shlex.quote(action_id)} --confirm {action_digest}"
                ),
                "spec": label_spec,
            }
        )

    identities = [item["id"] for item in actions]
    if len(identities) != len(set(identities)):
        raise portable.WorkflowError("publication action IDs must be unique")
    result = {
        "mr_state": cast(dict[str, Any], evidence["object"])["state"],
        "warning": "manual digest-confirmed publication; no action was executed",
        "preflight_path": preflight["path"],
        "preflight_sha256": preflight["sha256"],
        "helper_path": str(helper_path),
        "body_files": body_files,
        "actions": actions,
    }
    if not portable.review_publication_preview_is_valid(result):
        raise portable.WorkflowError("structured review publication preview is invalid")
    return result, enriched_findings, enriched_issues, enriched_threads


def review_markdown(
    evidence: dict[str, Any],
    context: dict[str, Any],
    decision: dict[str, Any],
    content: dict[str, Any],
    metadata: dict[str, Any],
    publication: dict[str, Any],
) -> str:
    assessment = cast(dict[str, dict[str, Any]], metadata["assessment"])
    presentation = cast(dict[str, Any], content["presentation"])
    previous = cast(list[dict[str, Any]], content["previous_finding_assessments"])
    finding_publications = {
        item["finding_id"]: item
        for item in cast(list[dict[str, Any]], content["finding_publications"])
    }
    recommended_issues = cast(list[dict[str, Any]], content["recommended_issues"])
    bodies = {
        item["publication_id"]: item
        for item in cast(list[dict[str, Any]], publication["body_files"])
    }
    publication_actions = cast(list[dict[str, Any]], publication["actions"])
    actions_by_publication = {
        item["publication_id"]: item
        for item in publication_actions
        if item["publication_id"] is not None
    }
    lines = [
        f"# {presentation['title']}",
        "",
        *([presentation["incremental_notice"], ""] if presentation["incremental_notice"] else []),
        f"- {presentation['target_label']}: {context['target'].get('url')}",
        f"- {presentation['role_label']}: {presentation['role_value']}",
        f"- {presentation['verdict_label']}: {presentation['verdict_value']}",
        f"- {presentation['publication_warning']}",
        "",
        content["summary"],
        "",
        f"## {presentation['metadata_heading']}",
        "",
    ]
    for field in ("title", "description", "labels", "workflow_state", "overall"):
        item = assessment[field]
        lines.extend([f"### `{field}`", "", item["rationale"]])
        if item["recommendation"]:
            lines.extend(["", cast(str, item["recommendation"])])
        lines.append("")

    label_review = cast(dict[str, Any], content["label_review"])
    label_assessments = {
        item["name"]: item for item in cast(list[dict[str, Any]], label_review["assessments"])
    }
    lines.extend([f"## {presentation['labels_heading']}", ""])
    for field in ("current", "add", "remove", "unresolved"):
        values = cast(list[str], label_review[field])
        rendered = (
            ", ".join(f"`{value}`" for value in values) if values else presentation["no_items"]
        )
        lines.extend([f"- `{field}`: {rendered}"])
    relevant = sorted(
        set(cast(list[str], label_review["add"]))
        | set(cast(list[str], label_review["remove"]))
        | set(cast(list[str], label_review["unresolved"])),
        key=str.casefold,
    )
    if relevant:
        lines.append("")
        lines.extend(f"- `{name}`: {label_assessments[name]['rationale']}" for name in relevant)
    lines.append("")

    lines.extend([f"## {presentation['previous_findings_heading']}", ""])
    if not previous:
        lines.extend([presentation["no_items"], ""])
    else:
        headers = cast(list[str], presentation["previous_table_headers"])
        lines.extend(
            [
                "| " + " | ".join(headers) + " |",
                "|" + "|".join("---" for _ in headers) + "|",
            ]
        )
        for item in previous:
            lines.append(
                "| "
                + " | ".join(
                    markdown_cell(item[key])
                    for key in (
                        "id",
                        "previous_status",
                        "current_status",
                        "rationale",
                        "action",
                    )
                )
                + " |"
            )
        lines.append("")

    shown_actions: set[str] = set()

    def add_fix(fix: dict[str, Any]) -> None:
        lines.extend([f"`fix_mode:{fix['fix_mode']}`", ""])
        if fix["fix_mode"] == "suggestion":
            lines.extend(["`suggestion:validated`", ""])
            return
        if fix["fix_mode"] != "patch":
            return
        patch_path = cast(str, fix["patch_path"])
        lines.extend(
            [
                f"`{patch_path}` (`{fix['patch_sha256']}`)",
                "",
                "<details>",
                "<summary>Git patch</summary>",
                "",
                "```diff",
                cast(str, fix["patch"]).rstrip(),
                "```",
                "",
                "</details>",
                "",
                "```shell",
                f"git apply --check {shlex.quote(patch_path)}",
                f"git apply {shlex.quote(patch_path)}",
                "```",
                "",
            ]
        )

    def add_action(action: dict[str, Any]) -> None:
        publication_id = action["publication_id"]
        body = bodies.get(publication_id) if publication_id is not None else None
        shown_actions.add(cast(str, action["id"]))
        lines.extend(
            [
                f"### `{action['id']}`",
                "",
                f"`action-sha256:{action['sha256']}`",
                "",
                f"`operation:{action['operation']}`",
                "",
            ]
        )
        mutation = cast(dict[str, Any], action["spec"]["mutation"])
        expected_thread = cast(dict[str, Any] | None, action["spec"]["expected"]["thread"])
        if portable.nonempty_string(mutation.get("path")):
            anchor = mutation.get("line") or mutation.get("old_line")
            lines.extend([f"`position:{mutation['path']}:{anchor}`", ""])
        elif expected_thread is not None and portable.nonempty_string(expected_thread.get("path")):
            lines.extend([f"`position:{expected_thread['path']}:{expected_thread['line']}`", ""])
        if body is not None:
            lines.extend(
                [
                    f"`{body['path']}` (`{body['sha256']}`)",
                    "",
                    portable.marked_preview(
                        f"PUBLICATION {publication_id} BODY", cast(str, body["content"])
                    ),
                    "",
                ]
            )
        lines.extend(["```shell", cast(str, action["command"]), "```"])
        if action["operation"] in {"resolve", "reopen"}:
            lines.extend(
                [
                    "",
                    presentation["recovery_label"],
                    "",
                    "```shell",
                    cast(str, action["command"]),
                    "```",
                ]
            )
        lines.append("")

    def add_publication_action(publication_id: str) -> None:
        action = actions_by_publication.get(publication_id)
        if action is None:
            return
        add_action(action)

    for item in previous:
        if item["publication_action"] != "no_publication":
            add_publication_action(cast(str, item["id"]))

    thread_decisions = cast(list[dict[str, Any]], content["thread_decisions"])

    def add_thread_section(heading: str, items: list[dict[str, Any]]) -> None:
        lines.extend([f"## {heading}", ""])
        if not items:
            lines.extend([presentation["no_items"], ""])
            return
        for item in items:
            lines.extend([f"### [{item['id']}]({item['url']})", "", item["rationale"], ""])
            add_fix(item)
            add_publication_action(f"thread-{item['id']}")

    add_thread_section(
        cast(str, presentation["open_threads_heading"]),
        [
            item
            for item in thread_decisions
            if item["state"] != "resolved"
            and item["outcome"] not in {"no_publication", "local_fix"}
        ],
    )
    add_thread_section(
        cast(str, presentation["closed_threads_heading"]),
        [
            item
            for item in thread_decisions
            if item["state"] == "resolved"
            and item["outcome"] not in {"no_publication", "local_fix"}
        ],
    )

    findings = cast(list[dict[str, Any]], content["findings"])
    local_threads = [item for item in thread_decisions if item["outcome"] == "local_fix"]
    lines.extend([f"## {presentation['local_fixes_heading']}", ""])
    if not local_threads and (context["role"] != "author" or not findings):
        lines.extend([presentation["no_items"], ""])
    for item in local_threads:
        lines.extend(
            [
                f"### [{item['id']}]({item['url']})",
                "",
                item["rationale"],
                "",
                cast(str, item["proposed_response"]),
                "",
            ]
        )
        add_fix(item)
    if context["role"] == "author":
        for finding in findings:
            publication_spec = finding_publications[finding["id"]]
            lines.extend(
                [
                    f"### {finding['summary']}",
                    "",
                    f"`{finding['id']}` · {presentation['severity_labels'][finding['severity']]}",
                    "",
                    finding["risk"],
                    "",
                    finding["minimum_fix"],
                    "",
                ]
            )
            add_fix(publication_spec)

    lines.extend([f"## {presentation['new_findings_heading']}", ""])
    reviewer_findings = findings if context["role"] == "reviewer" else []
    if not reviewer_findings:
        lines.extend([presentation["no_items"], ""])
    for finding in reviewer_findings:
        reviewer_publication = finding_publications.get(finding["id"])
        lines.extend(
            [
                f"### {finding['summary']}",
                "",
                f"`{finding['id']}` · {presentation['severity_labels'][finding['severity']]}",
                "",
                finding["risk"],
                "",
                finding["consequence"],
                "",
                f"**{presentation['evidence_label']}**",
                "",
                *[f"- {value}" for value in finding["evidence"]],
                "",
                f"**{presentation['relation_label']}**",
                "",
                finding["relation_to_change"],
                "",
                finding["minimum_fix"],
                "",
            ]
        )
        if reviewer_publication is not None and reviewer_publication["type"] == "line":
            line = reviewer_publication["line"] or reviewer_publication["old_line"]
            lines.extend([f"`{reviewer_publication['path']}:{line}`", ""])
        if reviewer_publication is not None:
            add_fix(reviewer_publication)
        if finding["id"] in finding_publications:
            add_publication_action(cast(str, finding["id"]))

    lines.extend([f"## {presentation['recommended_issues_heading']}", ""])
    if not recommended_issues:
        lines.extend([presentation["no_items"], ""])
    for issue in recommended_issues:
        lines.extend(
            [
                f"### {issue['title']}",
                "",
                f"`{issue['id']}`",
                "",
                issue["problem"],
                "",
                issue["risk"],
                "",
                f"**{presentation['evidence_label']}**",
                "",
                *[f"- {value}" for value in issue["evidence"]],
                "",
                issue["reason_out_of_scope"],
                "",
                issue["minimum_fix"],
                "",
            ]
        )
        add_publication_action(cast(str, issue["id"]))

    lines.extend([f"## {presentation['checked_heading']}", ""])
    without_publication = [
        item
        for item in cast(list[dict[str, Any]], content["thread_decisions"])
        if item["outcome"] == "no_publication"
    ]
    if not without_publication:
        lines.extend([presentation["no_items"], ""])
    else:
        lines.extend(
            f"- [{item['id']}]({item['url']}): {item['rationale']} (`fix_mode:{item['fix_mode']}`)"
            for item in without_publication
        )
        lines.append("")

    lines.extend(
        [
            f"## {presentation['architecture_heading']}",
            "",
            content["architecture_assessment"],
            "",
            f"## {presentation['semver_heading']}",
            "",
            f"`{content['semver_impact']}`",
            "",
            content["semver_rationale"],
            "",
            f"## {presentation['checks_heading']}",
            "",
            *[f"- {value}" for value in content["checks"]],
            "",
            f"## {presentation['publication_heading']}",
            "",
            presentation["publication_warning"],
            "",
            f"`{publication['preflight_path']}` (`{publication['preflight_sha256']}`)",
            "",
            f"`{publication['helper_path']}`",
        ]
    )
    for action in publication_actions:
        if action["id"] in shown_actions:
            continue
        lines.append("")
        add_action(action)
    return "\n".join(lines) + "\n"


@contextmanager
def review_state_lock(root: Path) -> Iterator[None]:
    path = root / ".review-state.lock"
    if path.is_symlink():
        raise portable.WorkflowError("review state lock must not be a symbolic link")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def replace_private_bytes(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.urandom(8).hex()}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def publish_review_state(
    root: Path,
    markdown: str,
    plan_path: Path,
    plan_digest: str,
    target: dict[str, Any],
    expected_incremental_baseline_state_digest: str | None,
    expected_progress: dict[str, object],
) -> tuple[Path, str]:
    markdown_path = root / "review-publication.md"
    baseline_path = root / BASELINE_NAME
    current_progress_path = progress_path(root)
    markdown_digest = hashlib.sha256(markdown.encode()).hexdigest()
    with review_state_lock(root):
        if (
            markdown_path.is_symlink()
            or baseline_path.is_symlink()
            or current_progress_path.is_symlink()
        ):
            raise portable.WorkflowError("review state paths must not be symbolic links")
        current_progress = validate_progress(
            portable.read_json(current_progress_path, "code-review progress"), root
        )
        if not set(expected_progress).issubset(current_progress) or any(
            current_progress[key] != value for key, value in expected_progress.items()
        ):
            raise portable.WorkflowError("code-review progress changed before publication")
        previous_markdown = markdown_path.read_bytes() if markdown_path.exists() else None
        previous_baseline = baseline_path.read_bytes() if baseline_path.exists() else None
        previous_progress = current_progress_path.read_bytes()
        actual_incremental_baseline_state_digest = (
            hashlib.sha256(previous_baseline).hexdigest() if previous_baseline is not None else None
        )
        if actual_incremental_baseline_state_digest != expected_incremental_baseline_state_digest:
            raise portable.WorkflowError("code-review baseline changed before publication")
        next_progress = {
            **current_progress,
            "stage": "plan_ready",
            "plan_path": str(plan_path),
            "plan_digest": plan_digest,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        validate_progress(next_progress, root)
        try:
            replace_private_bytes(markdown_path, markdown.encode())
            portable.write_json(current_progress_path, next_progress)
            portable.write_json(
                baseline_path,
                {
                    "contract_version": INCREMENTAL_CONTRACT_VERSION,
                    "target": target,
                    "plan_path": str(plan_path),
                    "plan_digest": plan_digest,
                    "markdown_path": str(markdown_path),
                    "markdown_digest": markdown_digest,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )
            directory_fd = os.open(root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except (OSError, portable.WorkflowError, UnicodeDecodeError):
            if previous_markdown is None:
                markdown_path.unlink(missing_ok=True)
            else:
                replace_private_bytes(markdown_path, previous_markdown)
            if previous_baseline is None:
                baseline_path.unlink(missing_ok=True)
            else:
                replace_private_bytes(baseline_path, previous_baseline)
            replace_private_bytes(current_progress_path, previous_progress)
            directory_fd = os.open(root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            raise
    return markdown_path.resolve(), markdown_digest


def reject_visible_raw_refs(
    markdown: str, evidence: dict[str, Any], context: dict[str, Any] | None = None
) -> None:
    refs = [
        value
        for value in (evidence.get("base_sha"), evidence.get("start_sha"), evidence.get("head_sha"))
        if isinstance(value, str) and len(value) >= 12
    ]
    if context is not None:
        incremental = context.get("incremental")
        delta = incremental.get("incremental_delta") if isinstance(incremental, dict) else None
        if isinstance(delta, dict):
            refs.extend(
                value
                for value in (delta.get("from_head"), delta.get("to_head"))
                if isinstance(value, str) and len(value) >= 12 and value not in refs
            )
    for line in markdown.splitlines():
        visible = re.sub(r"\]\(https?://[^)]*\)", "](...)", line).casefold()
        for value in refs:
            normalized = value.casefold()
            if normalized in visible or any(
                re.search(
                    rf"(?<![0-9a-f]){re.escape(normalized[:length])}(?![0-9a-f])",
                    visible,
                )
                for length in range(7, min(12, len(normalized)) + 1)
            ):
                raise portable.WorkflowError("user-facing review Markdown exposes a raw commit SHA")


def build_finding_ledger(
    incremental: dict[str, Any],
    assessments: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    publications: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    publication_preview: dict[str, Any],
) -> list[dict[str, Any]]:
    previous = {
        str(item["id"]): item
        for item in cast(list[dict[str, Any]], incremental.get("previous_finding_ledger", []))
    }
    assessment_by_id = {str(item["id"]): item for item in assessments}
    finding_by_id = {str(item["id"]): item for item in findings}
    publication_by_id = {str(item["finding_id"]): item for item in publications}
    issue_by_id = {str(item["id"]): item for item in issues}
    action_revisions: dict[str, int] = {}
    for body in cast(list[dict[str, Any]], publication_preview.get("body_files", [])):
        item_id, revision = str(body["publication_id"]), int(body["revision"])
        action_revisions[item_id] = max(action_revisions.get(item_id, 0), revision)
    ledger: list[dict[str, Any]] = []
    for item_id, old in previous.items():
        assessment = assessment_by_id[item_id]
        if old["kind"] == "finding" and item_id in finding_by_id:
            record = {
                "finding": finding_by_id[item_id],
                "publication": publication_by_id[item_id],
            }
            revision = publication_by_id[item_id]["revision"]
        elif old["kind"] == "issue" and item_id in issue_by_id:
            record = {"issue": issue_by_id[item_id]}
            revision = issue_by_id[item_id]["revision"]
        else:
            record = dict(cast(dict[str, Any], old["record"]))
            revision = old["revision"]
            if old["kind"] == "finding" and assessment["publication_action"] != "no_publication":
                publication = dict(record["publication"])
                publication["body"] = assessment["publication_body"]
                publication["revision"] = max(revision, action_revisions.get(item_id, revision))
                record["publication"] = publication
        ledger.append(
            {
                "id": item_id,
                "kind": old["kind"],
                "status": assessment["status"],
                "revision": max(revision, action_revisions.get(item_id, 0)),
                "record": record,
            }
        )
    for item_id, finding in finding_by_id.items():
        if item_id not in previous:
            publication = publication_by_id[item_id]
            ledger.append(
                {
                    "id": item_id,
                    "kind": "finding",
                    "status": "active",
                    "revision": publication["revision"],
                    "record": {"finding": finding, "publication": publication},
                }
            )
    for item_id, issue in issue_by_id.items():
        if item_id not in previous:
            ledger.append(
                {
                    "id": item_id,
                    "kind": "issue",
                    "status": "active",
                    "revision": issue["revision"],
                    "record": {"issue": issue},
                }
            )
    return sorted(ledger, key=lambda item: item["id"])


def build_publication_ledger(
    incremental: dict[str, Any], markers: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    ledger = {
        (item["id"], item["revision"], item["kind"]): item
        for item in cast(list[dict[str, Any]], incremental.get("previous_publication_ledger", []))
    }
    for marker in markers:
        identity = (marker["id"], marker["revision"], marker["kind"])
        existing = ledger.get(identity)
        if existing is not None and existing != marker:
            raise portable.WorkflowError("publication marker ledger binding changed")
        ledger[identity] = marker
    return sorted(ledger.values(), key=lambda item: (item["id"], item["revision"], item["kind"]))


def build_rejected_candidate_ledger(
    incremental: dict[str, Any],
    rejected_candidates: list[dict[str, Any]],
    assessments: list[dict[str, Any]],
    accepted_finding_ids: set[str],
) -> list[dict[str, Any]]:
    previous = {
        str(item["id"]): item
        for item in cast(list[dict[str, Any]], incremental.get("previous_rejected_candidates", []))
    }
    current = {str(item["id"]): item for item in rejected_candidates}
    assessment_by_id = {str(item["id"]): item for item in assessments}
    ledger: dict[str, dict[str, Any]] = {}
    for item_id, item in previous.items():
        assessment = assessment_by_id.get(item_id)
        if assessment is None:
            ledger[item_id] = item
        elif assessment["decision"] == "promoted":
            if item_id not in accepted_finding_ids:
                raise portable.WorkflowError(
                    "a promoted rejected candidate must become an accepted finding"
                )
        elif item_id not in current:
            raise portable.WorkflowError(
                "a still-rejected affected candidate must be recorded again"
            )
        else:
            ledger[item_id] = current[item_id]
    for item_id, item in current.items():
        if item_id not in previous:
            ledger[item_id] = item
    return sorted(ledger.values(), key=lambda item: item["id"])


def scaffold_review(
    evidence_value: str,
    context_value: str,
    decision_value: str,
    content_value: str,
) -> dict[str, object]:
    evidence_path, evidence, root, evidence_digest = evidence_context(evidence_value)
    _, context, context_digest = validate_context_binding(context_value, evidence_path)
    _, decision, decision_digest = content_addressed_artifact(
        decision_value, root, "review_decision"
    )
    if (
        decision.get("evidence_digest") != evidence_digest
        or decision.get("context_digest") != context_digest
    ):
        raise portable.WorkflowError("review decision does not bind evidence and context")
    target = evidence.get("target")
    if not isinstance(target, dict):
        raise portable.WorkflowError("review evidence target is unavailable")
    current_evidence = portable.collect(target, "code-review", persist=False)
    current_context = refresh_context(context, evidence_path)
    if (
        current_evidence.get("retrieval_complete") is not True
        or portable.fingerprint(evidence) != portable.fingerprint(current_evidence)
        or context.get("complete") is not True
        or current_context.get("complete") is not True
        or not contexts_match(context, current_context)
    ):
        raise portable.WorkflowError("review evidence or context is stale before plan creation")
    content = portable.exact_keys(
        portable.read_json(Path(content_value), "review plan content"),
        {
            "locale",
            "chat_assessment",
            "summary",
            "architecture_assessment",
            "semver_impact",
            "semver_rationale",
            "mr_metadata_assessment",
            "label_assessments",
            "checks",
            "findings",
            "finding_publications",
            "previous_finding_assessments",
            "recommended_issues",
            "rejected_candidates",
            "rejected_candidate_assessments",
            "thread_decisions",
        },
        "review plan content",
    )
    if (
        content["locale"] not in SUPPORTED_LOCALES
        or not portable.nonempty_string(content["summary"])
        or not portable.nonempty_string(content["architecture_assessment"])
        or content["semver_impact"] not in {"major", "minor", "patch", "none", "not_applicable"}
        or not portable.nonempty_string(content["semver_rationale"])
        or not isinstance(content["checks"], list)
        or not all(portable.nonempty_string(value) for value in content["checks"])
        or not portable.detailed_findings_are_valid(content["findings"])
        or not portable.thread_decisions_are_valid(content["thread_decisions"])
    ):
        raise portable.WorkflowError("review plan content is invalid")
    progress = load_progress(root)
    if progress is not None and content["locale"] != progress.get("locale"):
        raise portable.WorkflowError(
            "review content locale does not match selected progress locale"
        )
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings = cast(list[dict[str, Any]], content["findings"])
    finding_ids = [finding["id"] for finding in findings]
    if len(finding_ids) != len(set(finding_ids)) or any(
        str(finding_id).startswith("thread-")
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", str(finding_id)) is None
        for finding_id in finding_ids
    ):
        raise portable.WorkflowError("review finding IDs must be unique")
    if findings != sorted(findings, key=lambda item: severity_order[item["severity"]]):
        raise portable.WorkflowError("review findings must be ordered by severity")
    accepted_findings = cast(
        list[dict[str, Any]], decision.get("accepted_findings", decision.get("findings", []))
    )
    if accepted_findings != findings:
        raise portable.WorkflowError("review plan findings do not match the review decision")
    incremental = cast(dict[str, Any], context["incremental"])
    incremental_mode = str(incremental["mode"])
    if incremental_mode == "unchanged":
        raise portable.WorkflowError("an unchanged MR does not require a new review plan")
    if (incremental_mode == "incremental") != (decision.get("mode") == "incremental"):
        raise portable.WorkflowError("review decision mode does not match incremental context")
    chat_assessment = validate_chat_assessment(content["chat_assessment"])
    presentation = validate_presentation(
        localized_presentation(
            cast(str, content["locale"]),
            cast(str, context["role"]),
            cast(str, decision["verdict"]),
            incremental_mode,
        ),
        incremental_mode,
    )
    label_review = validate_label_assessments(
        evidence, content["label_assessments"], cast(str, content["semver_impact"])
    )
    previous_findings = cast(list[dict[str, Any]], incremental["previous_findings"])
    previous_issues = cast(list[dict[str, Any]], incremental["previous_recommended_issues"])
    previous_assessments = validate_previous_assessments(
        content["previous_finding_assessments"], previous_findings, previous_issues
    )
    reconsidered_rejected = cast(
        list[dict[str, Any]], incremental["reconsidered_rejected_candidates"]
    )
    rejected_candidate_assessments = validate_rejected_candidate_assessments(
        content["rejected_candidate_assessments"], reconsidered_rejected
    )
    rejected_candidates = validate_rejected_candidates(content["rejected_candidates"], decision)
    recommended_issues = validate_recommended_issues(content["recommended_issues"])
    issue_ids = [str(item["id"]) for item in recommended_issues]
    if (
        len(issue_ids) != len(set(issue_ids))
        or set(issue_ids) & set(finding_ids)
        or any(
            issue_id.startswith("thread-")
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", issue_id) is None
            for issue_id in issue_ids
        )
    ):
        raise portable.WorkflowError("finding and recommended issue IDs must be unique")
    assessment_by_id = {item["id"]: item for item in previous_assessments}
    previous_ledger_by_id = {
        str(item["id"]): item
        for item in cast(list[dict[str, Any]], incremental["previous_finding_ledger"])
    }
    observed_markers = marker_index(context)
    previous_finding_ids = {str(item["id"]) for item in previous_findings}
    previous_issue_ids = {str(item["id"]) for item in previous_issues}
    current_finding_ids = set(finding_ids)
    current_issue_ids = set(issue_ids)
    for item_id, kind in {
        **{value: "finding" for value in previous_finding_ids},
        **{value: "issue" for value in previous_issue_ids},
    }.items():
        assessment_item = assessment_by_id[item_id]
        observed_marker = observed_markers.get(item_id)
        if (
            kind == "finding"
            and observed_marker is not None
            and previous_ledger_by_id[item_id]["revision"] > observed_marker["revision"]
            and assessment_item["status"] in {"active", "changed", "unverified"}
            and assessment_item["publication_action"] == "no_publication"
        ):
            raise portable.WorkflowError(
                "a prepared but unpublished finding revision still requires publication"
            )
        if (
            previous_ledger_by_id[item_id]["status"] in {"fixed", "withdrawn"}
            and assessment_item["status"] == "active"
        ):
            raise portable.WorkflowError("a reopened historical finding must use changed status")
        present = item_id in (current_finding_ids if kind == "finding" else current_issue_ids)
        if assessment_item["status"] in {"active", "changed", "unverified"} and not present:
            raise portable.WorkflowError("an active previous finding disappeared from the plan")
        if assessment_item["status"] in {"fixed", "withdrawn"} and present:
            raise portable.WorkflowError("a closed previous finding remains active in the plan")
    if (
        any(item["status"] == "unverified" for item in previous_assessments)
        and decision.get("verdict") == "ready"
    ):
        raise portable.WorkflowError("an unverified previous finding prohibits ready")
    targeted_previous_findings = {
        str(item["id"]) for item in previous_assessments if item["critic_required"] is True
    }
    critic_targets = set(cast(list[str], decision.get("critic_target_finding_ids", [])))
    if not targeted_previous_findings.issubset(critic_targets):
        raise portable.WorkflowError(
            "changed or disputed previous findings require targeted critic coverage"
        )
    finding_publications = validate_finding_publications(
        content["finding_publications"], current_finding_ids
    )
    exact_git = cast(dict[str, Any], context["exact_git"])
    repo_root = Path(cast(str, exact_git["repo_root"]))
    head_sha = cast(str, evidence["head_sha"])
    base_sha = cast(str, evidence["base_sha"])
    for item in finding_publications:
        if item["type"] == "line":
            old_lines, new_lines = changed_diff_lines(
                repo_root, base_sha, head_sha, cast(str, item["path"])
            )
            if item["line"] is not None and item["line"] not in new_lines:
                raise portable.WorkflowError("finding new-line position is not in the exact diff")
            if item["old_line"] is not None and item["old_line"] not in old_lines:
                raise portable.WorkflowError("finding old-line position is not in the exact diff")
        if item["fix_mode"] == "patch":
            validate_git_patch(repo_root, head_sha, cast(str, item["patch"]))
        else:
            validate_suggestion(
                cast(str, item["body"]),
                repo_root=repo_root,
                head_sha=head_sha,
                path=cast(str, item["path"]),
                line=cast(int, item["line"]),
            )
    current_publication_by_id = {str(item["finding_id"]): item for item in finding_publications}
    current_issue_by_id = {str(item["id"]): item for item in recommended_issues}
    for item_id, old in previous_ledger_by_id.items():
        if item_id in current_finding_ids and old["kind"] != "finding":
            raise portable.WorkflowError("a historical issue ID cannot become a finding ID")
        if item_id in current_issue_ids and old["kind"] != "issue":
            raise portable.WorkflowError("a historical finding ID cannot become an issue ID")
        assessment_item = assessment_by_id[item_id]
        if assessment_item["status"] not in {"active", "unverified"}:
            continue
        if old["kind"] == "finding" and item_id in current_finding_ids:
            old_publication = dict(cast(dict[str, Any], old["record"])["publication"])
            old_publication.pop("revision", None)
            old_publication.pop("patch_path", None)
            old_publication.pop("patch_sha256", None)
            current_publication = current_publication_by_id[item_id]
            if old_publication != current_publication:
                raise portable.WorkflowError(
                    "a changed finding publication must use changed status"
                )
        if old["kind"] == "issue" and item_id in current_issue_ids:
            old_issue = dict(cast(dict[str, Any], old["record"])["issue"])
            old_issue.pop("revision", None)
            if old_issue != current_issue_by_id[item_id]:
                raise portable.WorkflowError("a changed recommended issue must use changed status")
    for assessment_item in previous_assessments:
        item_id = str(assessment_item["id"])
        if (
            assessment_item["kind"] == "finding"
            and item_id in current_publication_by_id
            and assessment_item["publication_action"] != "no_publication"
            and current_publication_by_id[item_id]["body"] != assessment_item["publication_body"]
        ):
            raise portable.WorkflowError(
                "finding publication and previous-finding action bodies disagree"
            )
    if {item["finding_id"] for item in finding_publications} != current_finding_ids:
        raise portable.WorkflowError("every actionable finding requires one concrete fix")
    if context["role"] == "reviewer" and any(
        item["type"] == "local_fix" for item in finding_publications
    ):
        raise portable.WorkflowError("reviewer findings require GitLab publication positions")
    if context["role"] == "author" and any(
        item["type"] != "local_fix" for item in finding_publications
    ):
        raise portable.WorkflowError("author findings require read-only local fix patches")
    expected_threads = expected_thread_bindings(context)
    thread_decisions = cast(list[dict[str, Any]], content["thread_decisions"])
    actual_threads = {item["id"]: item for item in thread_decisions}
    if len(actual_threads) != len(thread_decisions) or set(actual_threads) != set(expected_threads):
        raise portable.WorkflowError("review plan must account for every non-system thread")
    for thread_id, item in actual_threads.items():
        if (
            item["outcome"] == "no_publication"
            and item["proposed_response"] is not None
            or item["outcome"] != "no_publication"
            and not portable.nonempty_string(item["proposed_response"])
        ):
            raise portable.WorkflowError("thread publication outcome and body disagree")
        if item["url"] != expected_threads[thread_id].get("url"):
            raise portable.WorkflowError("thread decision URL does not match review context")
        if (
            set(item)
            != {
                "id",
                "url",
                "state",
                "assessment",
                "rationale",
                "outcome",
                "proposed_response",
                "fix_mode",
                "patch",
                "last_note_id",
                "last_note_body_sha256",
            }
            or item["last_note_id"] != expected_threads[thread_id]["last_note_id"]
            or item["last_note_body_sha256"] != expected_threads[thread_id]["last_note_body_sha256"]
        ):
            raise portable.WorkflowError("thread decision does not bind the latest note")
        source = expected_threads[thread_id]
        validate_thread_fix(item, source, repo_root, head_sha)
        if item["outcome"] == "resolve" and (
            source.get("root_resolvable") is not True or source.get("root_resolved") is True
        ):
            raise portable.WorkflowError("resolve requires an open resolvable thread")
        if item["outcome"] == "resolve" and item["assessment"] not in {
            "fixed",
            "false_positive",
            "duplicate",
            "not_related",
            "neutral",
        }:
            raise portable.WorkflowError("resolve requires a closing thread assessment")
        if item["outcome"] == "reopen" and (
            source.get("root_resolvable") is not True or source.get("root_resolved") is not True
        ):
            raise portable.WorkflowError("reopen requires a resolved resolvable thread")
        if item["outcome"] == "reopen" and item["assessment"] not in {
            "accepted",
            "question",
        }:
            raise portable.WorkflowError("reopen requires an actionable thread assessment")
    if context["role"] == "reviewer" and any(
        item["outcome"] == "local_fix" for item in thread_decisions
    ):
        raise portable.WorkflowError("reviewer thread decisions cannot promise local fixes")
    metadata = metadata_assessment(evidence, content["mr_metadata_assessment"])
    publication, enriched_publications, enriched_issues, enriched_threads = (
        structured_publication_preview(
            evidence,
            context,
            root,
            findings,
            finding_publications,
            previous_assessments,
            thread_decisions,
            recommended_issues,
            label_review,
        )
    )
    render_content = {
        **content,
        "presentation": presentation,
        "label_review": label_review,
        "finding_publications": enriched_publications,
        "previous_finding_assessments": previous_assessments,
        "recommended_issues": enriched_issues,
        "thread_decisions": enriched_threads,
    }
    markdown = review_markdown(evidence, context, decision, render_content, metadata, publication)
    reject_visible_raw_refs(markdown, evidence, context)
    finding_ledger = build_finding_ledger(
        incremental,
        previous_assessments,
        findings,
        enriched_publications,
        enriched_issues,
        publication,
    )
    publication_ledger = build_publication_ledger(
        incremental, cast(list[dict[str, Any]], context["publication_markers"])
    )
    rejected_candidate_ledger = build_rejected_candidate_ledger(
        incremental,
        rejected_candidates,
        rejected_candidate_assessments,
        {str(item["id"]) for item in accepted_findings},
    )
    payload = {
        "profile": "code-review",
        "review_contract_version": REVIEW_CONTRACT_VERSION,
        "external_mutations": False,
        "evidence_digest": evidence_digest,
        "context_digest": context_digest,
        "decision_digest": decision_digest,
        "target": context["target"],
        "role": context["role"],
        "mode": decision["mode"],
        "locale": content["locale"],
        "incremental": incremental,
        "verdict": decision["verdict"],
        "complete": evidence.get("retrieval_complete") is True and context.get("complete") is True,
        "summary": content["summary"],
        "architecture_assessment": content["architecture_assessment"],
        "semver_impact": content["semver_impact"],
        "semver_rationale": content["semver_rationale"],
        "chat_assessment": chat_assessment,
        "mr_metadata_assessment": metadata,
        "label_review": label_review,
        "publication_preview": publication,
        "presentation": presentation,
        "checks": content["checks"],
        "findings": findings,
        "finding_publications": enriched_publications,
        "previous_finding_assessments": previous_assessments,
        "recommended_issues": enriched_issues,
        "finding_ledger": finding_ledger,
        "publication_ledger": publication_ledger,
        "rejected_candidates": rejected_candidates,
        "rejected_candidate_assessments": rejected_candidate_assessments,
        "rejected_candidate_ledger": rejected_candidate_ledger,
        "thread_decisions": enriched_threads,
        "markdown": markdown,
    }
    path, plan_digest = portable.write_artifact(root, "review_plan", payload)
    markdown_path, markdown_digest = publish_review_state(
        root,
        markdown,
        path,
        plan_digest,
        cast(dict[str, Any], context["target"]),
        cast(str | None, incremental["incremental_baseline"]["state_digest"]),
        {
            "stage": "content_missing",
            "evidence_path": str(evidence_path),
            "evidence_digest": evidence_digest,
            "context_path": str(Path(context_value).resolve()),
            "context_digest": context_digest,
            "decision_path": str(Path(decision_value).resolve()),
            "decision_digest": decision_digest,
        },
    )
    return {
        "status": "ok" if payload["complete"] else "incomplete",
        "summary": {
            "tldr": "Prepared an immutable role-aware code review plan.",
            "scope": [str(context["target"].get("url", ""))],
            "risks": [] if payload["complete"] else ["review evidence or context incomplete"],
            "checks": ["evidence binding", "role", "all threads", "detailed findings"],
        },
        "artifact_path": str(path),
        "digest": plan_digest,
        "markdown_path": str(markdown_path),
        "markdown_digest": markdown_digest,
        "publication_body_paths": [item["path"] for item in publication["body_files"]],
        "patch_paths": [
            item["patch_path"]
            for item in [*enriched_publications, *enriched_threads]
            if item["fix_mode"] == "patch"
        ],
        "publication_commands": [item["command"] for item in publication["actions"]],
        "publication_actions": [
            {"id": item["id"], "sha256": item["sha256"]} for item in publication["actions"]
        ],
        "stage": "plan_ready",
        "next_action": runner_action("report-review", "--artifact-root", str(root)),
        "external_mutations": False,
    }


def progress_artifact(
    root: Path, progress: dict[str, Any], prefix: str, kind: str
) -> tuple[Path, dict[str, Any], str] | None:
    path_value = progress.get(f"{prefix}_path")
    digest_value = progress.get(f"{prefix}_digest")
    if path_value is None and digest_value is None:
        return None
    if not isinstance(path_value, str) or not portable.is_digest(digest_value):
        raise portable.WorkflowError("code-review progress artifact binding is incomplete")
    path = portable.regular_file(Path(path_value), kind.replace("_", " "))
    expected = root / "artifacts" / kind / f"{digest_value}.json"
    if path != expected or hashlib.sha256(path.read_bytes()).hexdigest() != digest_value:
        raise portable.WorkflowError("code-review progress artifact binding changed")
    _, payload = portable.artifact_payload(path, kind)
    return path, payload, cast(str, digest_value)


def next_action_for_stage(
    stage: str, root: Path, progress: dict[str, Any]
) -> dict[str, Any] | None:
    if stage == "prepared":
        repo_root = cast(str | None, progress.get("repo_root"))
        mode = cast(str, progress.get("mode") or "normal")
        if mode in {"incremental", "unchanged"}:
            mode = "normal"
        return runner_action(
            "context",
            "--evidence",
            cast(str, progress["evidence_path"]),
            "--repo-root",
            repo_root or "<checkout>",
            "--incremental",
            cast(str, progress.get("incremental") or "auto"),
            "--review-mode",
            mode,
            "--locale",
            cast(str, progress.get("locale") or "en"),
            required_inputs=("repo_root",) if repo_root is None else (),
        )
    if stage == "critic_missing":
        return runner_action("template-review", "--artifact-root", str(root), "--kind", "critic")
    if stage in {"context_ready", "finalize_missing"}:
        return runner_action("finalize", "--artifact-root", str(root))
    if stage == "decision_missing":
        return runner_action("template-review", "--artifact-root", str(root), "--kind", "decision")
    if stage == "content_missing":
        return runner_action("template-review", "--artifact-root", str(root), "--kind", "content")
    if stage == "plan_ready":
        return runner_action("report-review", "--artifact-root", str(root))
    return None


def restart_action(
    root: Path, evidence: dict[str, Any], progress: dict[str, Any] | None
) -> dict[str, Any] | None:
    target = evidence.get("target")
    url = target.get("url") if isinstance(target, dict) else None
    if not portable.nonempty_string(url):
        return None
    arguments = ["--url", cast(str, url)]
    repo_root = progress.get("repo_root") if progress is not None else None
    mode = progress.get("mode") if progress is not None else None
    locale = progress.get("locale") if progress is not None else None
    incremental = progress.get("incremental") if progress is not None else None
    if isinstance(repo_root, str):
        arguments.extend(("--repo-root", repo_root))
    arguments.extend(
        (
            "--review-mode",
            cast(str, mode) if mode in {"fast", "normal", "deep"} else "normal",
            "--locale",
            cast(str, locale) if locale in SUPPORTED_LOCALES else "en",
            "--incremental",
            cast(str, incremental) if incremental in {"auto", "off"} else "auto",
        )
    )
    return runner_action("prepare", *arguments)


def _review_status(artifact_root: str) -> dict[str, Any]:
    root = portable.artifact_root(Path(artifact_root))
    evidence_path, evidence = review_evidence_from_root(root)
    evidence_digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    progress = load_progress(root) or empty_progress(evidence_path, evidence_digest)
    if (
        progress["evidence_path"] != str(evidence_path)
        or progress["evidence_digest"] != evidence_digest
    ):
        progress = empty_progress(evidence_path, evidence_digest)
    locale = cast(str, progress.get("locale") or "en")
    actual_stage = "prepared"
    reason = "review context has not been collected"
    context: dict[str, Any] | None = None
    context_artifact = progress_artifact(root, progress, "context", "review_context")
    if context_artifact is not None:
        context_path, context, context_digest = context_artifact
        if (
            context.get("evidence_digest") != evidence_digest
            or context.get("target") != evidence.get("target")
            or context.get("complete") is not True
        ):
            raise portable.WorkflowError("review context is stale or incomplete")
        progress["context_path"] = str(context_path)
        progress["context_digest"] = context_digest
        mode = progress.get("mode")
        if mode not in REVIEW_MODES:
            actual_stage = "context_ready"
            reason = "review mode has not been selected"
        elif mode == "unchanged":
            actual_stage = "plan_ready"
            reason = "the MR has not changed since the finalized baseline"
        else:
            critic_required = mode in {"normal", "deep", "incremental"}
            critic_artifact = progress_artifact(root, progress, "critic_receipt", "critic_receipt")
            if critic_required and critic_artifact is None:
                actual_stage = "critic_missing"
                reason = "an independent recorded critic receipt is required"
            else:
                if critic_artifact is not None:
                    _, critic, _ = critic_artifact
                    scope_digest = (
                        cast(dict[str, Any], context["incremental"])["incremental_delta_digest"]
                        if mode == "incremental"
                        else None
                    )
                    portable.validate_critic(critic, evidence_digest, scope_digest)
                finalize_artifact = progress_artifact(
                    root, progress, "finalize_report", "finalize_report"
                )
                if finalize_artifact is None:
                    actual_stage = "finalize_missing"
                    reason = "fresh evidence has not been finalized"
                else:
                    finalize_path, _, finalize_digest = finalize_artifact
                    portable.validate_finalize_report(finalize_path, evidence_path, evidence)
                    decision_artifact = progress_artifact(
                        root, progress, "decision", "review_decision"
                    )
                    if decision_artifact is None:
                        actual_stage = "decision_missing"
                        reason = "the finalized review decision is missing"
                    else:
                        _, decision, _ = decision_artifact
                        if (
                            decision.get("evidence_digest") != evidence_digest
                            or decision.get("context_digest") != progress["context_digest"]
                            or decision.get("finalize_digest") != finalize_digest
                            or decision.get("critic_receipt_digest")
                            != progress.get("critic_receipt_digest")
                            or decision.get("mode") != mode
                        ):
                            raise portable.WorkflowError("review decision is stale")
                        actual_stage = "content_missing"
                        reason = "the immutable review plan has not been created"

    stale_plan_reason: str | None = None
    plan: dict[str, Any] | None = None
    try:
        baseline = baseline_pointer(root)
    except portable.WorkflowError:
        baseline = None
        stale_plan_reason = "the stable publication plan is invalid"
    if baseline is not None:
        pointer, candidate = baseline
        unchanged = (
            context is not None
            and cast(dict[str, Any], context.get("incremental", {})).get("mode") == "unchanged"
            and cast(dict[str, Any], context["incremental"])
            .get("incremental_baseline", {})
            .get("plan_digest")
            == pointer.get("plan_digest")
        )
        current = (
            candidate.get("review_contract_version") == REVIEW_CONTRACT_VERSION
            and candidate.get("complete") is True
            and candidate.get("target") == evidence.get("target")
            and (
                unchanged
                or candidate.get("evidence_digest") == evidence_digest
                and candidate.get("context_digest") == progress.get("context_digest")
                and candidate.get("decision_digest") == progress.get("decision_digest")
            )
        )
        if current:
            plan = candidate
            actual_stage = "plan_ready"
            reason = (
                "the unchanged MR reuses the current finalized review plan"
                if unchanged
                else "the current review plan is complete and fresh"
            )
            progress["plan_path"] = pointer["plan_path"]
            progress["plan_digest"] = pointer["plan_digest"]
        else:
            stale_plan_reason = "the stable publication plan does not bind current evidence"
    elif (
        context is not None
        and cast(dict[str, Any], context.get("incremental", {})).get("mode") == "unchanged"
    ):
        stale_plan_reason = "the unchanged review baseline is missing"
        actual_stage = "prepared"
        reason = "collect context again before continuing"

    stage = (
        "stale" if stale_plan_reason is not None and actual_stage != "plan_ready" else actual_stage
    )
    next_stage = actual_stage if stage == "stale" else stage
    result = {
        "status": "ok" if actual_stage == "plan_ready" else "incomplete",
        "stage": stage,
        "resume_stage": next_stage if stage == "stale" else None,
        "reason": stale_plan_reason or reason,
        "stale_plan": stale_plan_reason is not None,
        "artifact_root": str(root),
        "evidence_path": str(evidence_path),
        "context_path": progress.get("context_path"),
        "mode": progress.get("mode"),
        "locale": locale,
        "publication_plan_path": str(root / "review-publication.md")
        if actual_stage == "plan_ready"
        else None,
        "plan_digest": progress.get("plan_digest") if plan is not None else None,
        "next_action": next_action_for_stage(next_stage, root, progress),
        "external_mutations": False,
    }
    return result


def review_status(artifact_root: str) -> dict[str, Any]:
    try:
        return _review_status(artifact_root)
    except (OSError, UnicodeDecodeError, portable.WorkflowError):
        root = portable.artifact_root(Path(artifact_root))
        try:
            _, evidence = review_evidence_from_root(root)
        except portable.WorkflowError:
            evidence = {}
        progress = None
        try:
            progress = load_progress(root)
        except portable.WorkflowError:
            pass
        return {
            "status": "incomplete",
            "stage": "stale",
            "resume_stage": "prepared",
            "reason": "review progress or a bound artifact is invalid",
            "stale_plan": True,
            "artifact_root": str(root),
            "evidence_path": None,
            "context_path": None,
            "mode": progress.get("mode") if progress is not None else None,
            "locale": progress.get("locale") if progress is not None else "en",
            "publication_plan_path": None,
            "plan_digest": None,
            "next_action": restart_action(root, evidence, progress),
            "external_mutations": False,
        }


def write_review_draft(root: Path, name: str, identity: str, value: dict[str, Any]) -> Path:
    directory = portable.private_directory(root / "review-drafts")
    path = directory / f"{name}-{identity[:16]}.json"
    with review_state_lock(root):
        if path.exists() or path.is_symlink():
            portable.regular_file(path, "review draft")
        else:
            portable.write_json(path, value)
    return path.resolve()


def content_template(
    evidence: dict[str, Any], context: dict[str, Any], decision: dict[str, Any], locale: str
) -> dict[str, Any]:
    incremental = cast(dict[str, Any], context["incremental"])
    accepted = cast(list[dict[str, Any]], decision.get("accepted_findings", []))
    primary_by_id = {
        str(item["id"]): item for item in cast(list[dict[str, Any]], decision.get("findings", []))
    }
    critic_by_id = {
        str(item["id"]): item
        for item in cast(list[dict[str, Any]], decision.get("critic_findings", []))
    }
    responses = {
        str(item["id"]): item for item in cast(list[dict[str, Any]], decision.get("responses", []))
    }
    rejected_candidates: list[dict[str, Any]] = []
    for item_id, finding in {**primary_by_id, **critic_by_id}.items():
        response = responses.get(item_id)
        if response is None or response.get("decision") != "reject":
            continue
        rejected_candidates.append(
            {
                "id": item_id,
                "source": "primary" if item_id in primary_by_id else "critic",
                "finding": finding,
                "reason": "",
                "paths": [],
                "thread_ids": [],
                "metadata_fields": [],
                "ci": False,
            }
        )
    previous_assessments = []
    for kind, values in (
        ("finding", cast(list[dict[str, Any]], incremental["previous_findings"])),
        ("issue", cast(list[dict[str, Any]], incremental["previous_recommended_issues"])),
    ):
        for item in values:
            previous_assessments.append(
                {
                    "id": str(item["id"]),
                    "kind": kind,
                    "status": "unverified",
                    "previous_status": "",
                    "current_status": "",
                    "rationale": "",
                    "action": "",
                    "publication_action": "no_publication",
                    "publication_body": None,
                    "critic_required": True,
                }
            )
    threads = []
    for thread_id, binding in expected_thread_bindings(context).items():
        threads.append(
            {
                "id": thread_id,
                "url": binding["url"],
                "state": binding["state"],
                "assessment": "neutral",
                "rationale": "",
                "outcome": "no_publication",
                "proposed_response": None,
                "fix_mode": "not_required",
                "patch": None,
                "last_note_id": binding["last_note_id"],
                "last_note_body_sha256": binding["last_note_body_sha256"],
            }
        )
    return {
        "locale": locale,
        "chat_assessment": {
            "necessity": {"status": "unconfirmed", "rationale": ""},
            "relevance": {"status": "current", "rationale": ""},
            "change": "",
        },
        "summary": "",
        "architecture_assessment": "",
        "semver_impact": "none",
        "semver_rationale": "",
        "mr_metadata_assessment": {
            field: {"status": "unverified", "rationale": "", "recommendation": None}
            for field in ("title", "description", "labels", "workflow_state", "overall")
        },
        "label_assessments": [
            {"name": item["name"], "status": "unresolved", "rationale": ""}
            for item in label_catalog(evidence)
        ],
        "checks": [],
        "findings": accepted,
        "finding_publications": [
            {
                "finding_id": item["id"],
                "type": "local_fix" if context["role"] == "author" else "general",
                "path": None,
                "line": None,
                "old_line": None,
                "body": "",
                "fix_mode": "patch",
                "patch": "",
            }
            for item in accepted
        ],
        "previous_finding_assessments": previous_assessments,
        "recommended_issues": [],
        "rejected_candidates": rejected_candidates,
        "rejected_candidate_assessments": [
            {"id": item["id"], "decision": "still_rejected", "reason": ""}
            for item in cast(list[dict[str, Any]], incremental["reconsidered_rejected_candidates"])
        ],
        "thread_decisions": threads,
    }


def template_review(artifact_root: str, kind: str) -> dict[str, Any]:
    status = review_status(artifact_root)
    root = portable.artifact_root(Path(artifact_root))
    progress = cast(dict[str, Any], load_progress(root))
    evidence_path, evidence = review_evidence_from_root(root)
    evidence_digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    context_artifact = progress_artifact(root, progress, "context", "review_context")
    if context_artifact is None:
        raise portable.WorkflowError("review context is required before template creation")
    context_path, context, context_digest = context_artifact
    mode = cast(str, progress["mode"])
    locale = cast(str, progress["locale"])
    if kind == "critic":
        expected_stage = status.get("resume_stage") or status["stage"]
        if expected_stage != "critic_missing":
            raise portable.WorkflowError("critic template is not the next review stage")
        incremental = cast(dict[str, Any], context["incremental"])
        value: dict[str, Any] = {
            "schema": "portable-gitlab/critic-receipt/v2",
            "evidence_digest": evidence_digest,
            "run_id": "",
            "session_id": "",
            "findings": [],
            "external_mutations": False,
        }
        if mode == "incremental":
            value["scope_digest"] = incremental["incremental_delta_digest"]
            value["target_finding_ids"] = sorted(
                str(item["id"])
                for item in cast(list[dict[str, Any]], incremental["previous_findings"])
            )
        identity = evidence_digest
    elif kind == "decision":
        expected_stage = status.get("resume_stage") or status["stage"]
        if expected_stage != "decision_missing":
            raise portable.WorkflowError("decision template is not the next review stage")
        finalize_artifact = cast(
            tuple[Path, dict[str, Any], str],
            progress_artifact(root, progress, "finalize_report", "finalize_report"),
        )
        _, _, finalize_digest = finalize_artifact
        critic_artifact = progress_artifact(root, progress, "critic_receipt", "critic_receipt")
        critic_findings = critic_artifact[1]["findings"] if critic_artifact is not None else []
        critic_digest = critic_artifact[2] if critic_artifact is not None else None
        open_threads = [
            {"id": f"thread:{thread_id}"}
            for thread_id, binding in expected_thread_bindings(context).items()
            if binding["state"] == "open"
        ]
        pipeline_status, _ = portable.pipeline_summary(evidence)
        failed_pipeline = pipeline_status == "failed"
        blocking_ids = [item["id"] for item in critic_findings if item.get("severity") != "low"]
        value = {
            "schema": "portable-gitlab/review-decision/v2",
            "evidence_digest": evidence_digest,
            "finalize_digest": finalize_digest,
            "context_digest": context_digest,
            "critic_receipt_digest": critic_digest,
            "mode": mode,
            "external_mutations": False,
            "verdict": "not_ready" if blocking_ids else "blocked" if failed_pipeline else "ready",
            "run_id": "",
            "session_id": "",
            "low_risk": mode == "fast",
            "blocking_findings": bool(blocking_ids),
            "blocking_finding_ids": blocking_ids,
            "owner_decision_reasons": [
                "The exact-head pipeline failed and job logs are unavailable."
            ]
            if failed_pipeline and not blocking_ids
            else [],
            "findings": [],
            "unresolved_threads": open_threads,
            "responses": [
                {"id": item["id"], "decision": "accept", "reason": ""}
                for item in [*critic_findings, *open_threads]
            ],
        }
        identity = finalize_digest
    elif kind == "content":
        expected_stage = status.get("resume_stage") or status["stage"]
        if expected_stage != "content_missing":
            raise portable.WorkflowError("content template is not the next review stage")
        decision_artifact = cast(
            tuple[Path, dict[str, Any], str],
            progress_artifact(root, progress, "decision", "review_decision"),
        )
        _, decision, decision_digest = decision_artifact
        value = content_template(evidence, context, decision, locale)
        identity = decision_digest
    else:
        raise portable.WorkflowError("review template kind must be critic, decision, or content")
    path = write_review_draft(root, kind, identity, value)
    if kind == "critic":
        next_action = runner_action(
            "record-artifact",
            "--kind",
            "critic_receipt",
            "--evidence",
            str(evidence_path),
            "--input",
            str(path),
        )
    elif kind == "decision":
        arguments = [
            "--evidence",
            str(evidence_path),
            "--report",
            str(path),
            "--context",
            str(context_path),
            "--finalize-report",
            cast(str, progress["finalize_report_path"]),
            "--mode",
            mode,
        ]
        if progress["critic_receipt_path"] is not None:
            arguments.extend(("--critic-receipt", cast(str, progress["critic_receipt_path"])))
        next_action = runner_action("finalize-review", *arguments)
    else:
        next_action = runner_action(
            "scaffold-review",
            "--evidence",
            str(evidence_path),
            "--context",
            str(context_path),
            "--decision",
            cast(str, progress["decision_path"]),
            "--content",
            str(path),
        )
    return {
        "status": "ok",
        "stage": status["stage"],
        "template_kind": kind,
        "template_path": str(path),
        "next_action": next_action,
        "external_mutations": False,
    }


def validate_review_verdict(
    report: dict[str, Any], accepted_findings: list[dict[str, Any]], evidence: dict[str, Any]
) -> None:
    accepted_by_id = {str(item["id"]): item for item in accepted_findings}
    expected_blocking_ids = {
        item_id for item_id, item in accepted_by_id.items() if item.get("severity") != "low"
    }
    blocking_value = report.get("blocking_finding_ids")
    if blocking_value is None:
        blocking_ids = {
            item_id for item_id, item in accepted_by_id.items() if item.get("severity") != "low"
        }
    elif not isinstance(blocking_value, list) or not all(
        portable.nonempty_string(item) for item in blocking_value
    ):
        raise portable.WorkflowError("blocking finding IDs are invalid")
    else:
        blocking_ids = set(cast(list[str], blocking_value))
    if (
        len(blocking_ids) != len(cast(list[str], blocking_value or list(blocking_ids)))
        or blocking_ids != expected_blocking_ids
        or report.get("blocking_findings") is not bool(blocking_ids)
    ):
        raise portable.WorkflowError("every accepted non-low finding must be blocking")
    reasons = report.get("owner_decision_reasons", [])
    if not isinstance(reasons, list) or not all(portable.nonempty_string(item) for item in reasons):
        raise portable.WorkflowError("owner decision reasons are invalid")
    pipeline_status, _ = portable.pipeline_summary(evidence)
    if blocking_ids:
        expected = "not_ready"
    elif pipeline_status == "failed":
        expected = "blocked"
    elif reasons:
        expected = "blocked"
    else:
        expected = "ready"
    if report.get("verdict") != expected:
        raise portable.WorkflowError(
            "review verdict does not match findings and exact-head pipeline"
        )


def blocked_chat(locale: str, stage: str, reason: str, action: object) -> str:
    command = cast(dict[str, Any], action).get("command") if isinstance(action, dict) else None
    labels = portable.code_review_chat_labels(locale)
    lines = [
        labels["blocked_title"],
        "",
        f"- **{labels['stage']}:** `{stage}`",
        f"- **{labels['reason']}:** {reason}",
    ]
    if command:
        lines.append(f"- **{labels['next_action']}:** `{command}`")
    return "\n".join(lines)


def review_chat(plan: dict[str, Any], context: dict[str, Any], plan_path: str) -> str:
    assessment = validate_chat_assessment(plan.get("chat_assessment"))
    presentation = cast(dict[str, Any], plan["presentation"])
    locale = cast(str, plan["locale"])
    metadata = cast(dict[str, Any], plan["mr_metadata_assessment"])["assessment"]["overall"]
    labels = portable.code_review_chat_labels(locale)
    exact_git = cast(dict[str, Any], context["exact_git"])
    semver = cast(str, plan["semver_impact"])
    semver_value = (
        semver.upper() if semver in {"major", "minor", "patch"} else semver.replace("_", " ")
    )
    necessity = cast(dict[str, Any], assessment["necessity"])
    relevance = cast(dict[str, Any], assessment["relevance"])
    necessity_values = cast(dict[str, str], labels["necessity_values"])
    relevance_values = cast(dict[str, str], labels["relevance_values"])
    metadata_values = cast(dict[str, str], labels["metadata_values"])
    lines = []
    if plan["mode"] == "incremental":
        lines.extend([presentation["incremental_notice"], ""])
    lines.extend(
        [
            cast(str, labels["title"]),
            "",
            f"- **{labels['role']}:** {presentation['role_value']}",
            f"- **{labels['necessity']}:** {necessity_values[necessity['status']]} - {necessity['rationale']}",
            f"- **{labels['relevance']}:** {relevance_values[relevance['status']]} - {relevance['rationale']}",
            f"- **{labels['change']}:** {assessment['change']}",
            f"- **{labels['architecture']}:** {plan['architecture_assessment']}",
            f"- **{labels['semver']}:** {semver_value} - {plan['semver_rationale']}",
            f"- **{labels['metadata']}:** {metadata_values[metadata['status']]}",
            f"- **{labels['verdict']}:** {presentation['verdict_value']}",
        ]
    )
    if not plan["findings"]:
        lines.append(f"- **{labels['findings']}:** {labels['none']}")
    lines.extend(
        [
            f"- **{labels['checkout']}:** `{exact_git['repo_root']}`",
            f"- **{labels['plan']}:** `{plan_path}`",
        ]
    )
    return "\n".join(lines)


def _report_review(artifact_root: str) -> dict[str, Any]:
    status = review_status(artifact_root)
    locale = cast(str, status.get("locale") or "en")
    if status["stage"] != "plan_ready":
        return {
            "status": "blocked",
            "stage": status["stage"],
            "reason": status["reason"],
            "chat": blocked_chat(
                locale,
                cast(str, status["stage"]),
                cast(str, status["reason"]),
                status["next_action"],
            ),
            "next_action": status["next_action"],
            "external_mutations": False,
        }
    root = portable.artifact_root(Path(artifact_root))
    baseline = baseline_pointer(root)
    if baseline is None:
        raise portable.WorkflowError("current review baseline is unavailable")
    pointer, plan = baseline
    evidence_path, evidence = review_evidence_from_root(root)
    progress = load_progress(root)
    if progress is None:
        raise portable.WorkflowError("code-review progress is unavailable")
    recovery = restart_action(root, evidence, progress)
    current = portable.collect(
        cast(dict[str, Any], evidence["target"]), "code-review", persist=False
    )
    if current.get("retrieval_complete") is not True or portable.fingerprint(
        current
    ) != portable.fingerprint(evidence):
        blocked = {**status, "stage": "stale", "reason": "review evidence changed before report"}
        return {
            "status": "blocked",
            "stage": "stale",
            "reason": blocked["reason"],
            "chat": blocked_chat(locale, "stale", cast(str, blocked["reason"]), recovery),
            "next_action": recovery,
            "external_mutations": False,
        }
    context_artifact = progress_artifact(root, progress, "context", "review_context")
    if context_artifact is None:
        raise portable.WorkflowError("current review context is unavailable")
    _, context, _ = context_artifact
    refreshed = refresh_context(context, evidence_path)
    report_context = dict(context)
    report_context.pop("incremental", None)
    report_context.pop("publication_markers", None)
    if refreshed.get("complete") is not True or not contexts_match(report_context, refreshed):
        return {
            "status": "blocked",
            "stage": "stale",
            "reason": "review context changed before report",
            "chat": blocked_chat(locale, "stale", "review context changed before report", recovery),
            "next_action": recovery,
            "external_mutations": False,
        }
    chat = review_chat(plan, context, cast(str, pointer["markdown_path"]))
    reject_visible_raw_refs(chat, evidence, context)
    return {
        "status": "ok",
        "stage": "plan_ready",
        "chat": chat,
        "publication_plan_path": pointer["markdown_path"],
        "plan_digest": pointer["plan_digest"],
        "next_action": None,
        "external_mutations": False,
    }


def report_review(artifact_root: str) -> dict[str, Any]:
    try:
        return _report_review(artifact_root)
    except (OSError, UnicodeDecodeError, portable.WorkflowError):
        reason = "review state could not be safely revalidated"
        next_action = None
        locale = "en"
        try:
            root = portable.artifact_root(Path(artifact_root))
            _, evidence = review_evidence_from_root(root)
            try:
                progress = load_progress(root)
            except portable.WorkflowError:
                progress = None
            if progress is not None and progress.get("locale") in SUPPORTED_LOCALES:
                locale = cast(str, progress["locale"])
            next_action = restart_action(root, evidence, progress)
        except portable.WorkflowError:
            pass
        return {
            "status": "blocked",
            "stage": "stale",
            "reason": reason,
            "chat": blocked_chat(locale, "stale", reason, next_action),
            "next_action": next_action,
            "external_mutations": False,
        }
