#!/usr/bin/env python3
"""Build an exact release inventory bound to a release MR evidence snapshot."""

from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote as urlquote

if TYPE_CHECKING:
    from shared.references.portable_gitlab import contract as portable
else:
    from portable_runtime import contract as portable

DEFAULT_WORKERS = 8
MAX_WORKERS = 32
MAX_RELEASE_COMMITS = 10_000
MAX_RELEASE_TAGS = 10_000
MAX_COMPONENT_MRS = 1_000
MAX_WORK_ITEMS = 250
COMMIT_METADATA_FIELDS = 5
MR_FIELDS = (
    "id",
    "iid",
    "title",
    "description",
    "labels",
    "author",
    "web_url",
    "source_branch",
    "target_branch",
    "merge_commit_sha",
    "squash_commit_sha",
    "merged_at",
    "state",
)
TECHNICAL_SUBJECT_RE = re.compile(
    r"(?:\[skip\s+ci\])|(?:^(?:bump|update)\s+v?\d+\.\d+\.\d+(?:\s|$))",
    re.IGNORECASE,
)


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


def resolve_commit(root: Path, revision: str) -> str:
    value = str(portable.git_read(root, "rev-parse", "--verify", f"{revision}^{{commit}}"))
    sha = value.strip()
    if re.fullmatch(r"[0-9a-fA-F]{1,128}", sha) is None:
        raise portable.WorkflowError("Git returned an invalid commit SHA")
    return sha


def first_parent_tag(root: Path, head_sha: str) -> str | None:
    raw_tags = str(
        portable.git_read(
            root,
            "for-each-ref",
            f"--count={MAX_RELEASE_TAGS + 1}",
            "--format=%(refname:strip=2)%00%(*objectname)%00%(objectname)",
            "refs/tags/v*",
        )
    )
    if len(raw_tags.encode()) > portable.MAX_BYTES:
        raise portable.WorkflowError("local tag list exceeds the size limit")
    tag_lines = raw_tags.splitlines()
    if len(tag_lines) > MAX_RELEASE_TAGS:
        raise portable.WorkflowError("local tag list exceeds the protective limit")

    tags_by_commit: dict[str, list[tuple[tuple[int, int, int], str]]] = {}
    for line in tag_lines:
        fields = line.split("\0")
        if len(fields) != 3:
            raise portable.WorkflowError("Git returned an invalid local tag list")
        name, peeled_sha, object_sha = fields
        version = portable.parse_semver(name[1:]) if name.startswith("v") else None
        if version is None or version[0] < 1 or version[3] or version[4]:
            continue
        commit_sha = peeled_sha or object_sha
        if re.fullmatch(r"[0-9a-fA-F]{1,128}", commit_sha) is None:
            raise portable.WorkflowError("Git returned an invalid tagged object SHA")
        tags_by_commit.setdefault(commit_sha.lower(), []).append((version[:3], name))
    if not tags_by_commit:
        return None

    raw_commits = str(
        portable.git_read(
            root,
            "rev-list",
            "--first-parent",
            f"--max-count={MAX_RELEASE_COMMITS + 1}",
            head_sha,
        )
    )
    if len(raw_commits.encode()) > portable.MAX_BYTES:
        raise portable.WorkflowError("first-parent history exceeds the size limit")
    commits = [line for line in raw_commits.splitlines() if line]
    if len(commits) > MAX_RELEASE_COMMITS:
        raise portable.WorkflowError("first-parent history exceeds the protective limit")
    for commit_sha in commits:
        if re.fullmatch(r"[0-9a-fA-F]{1,128}", commit_sha) is None:
            raise portable.WorkflowError("Git returned an invalid first-parent commit SHA")
        candidates = tags_by_commit.get(commit_sha.lower())
        if candidates:
            return max(candidates)[1]
    return None


def exact_local_tag(root: Path, reference: str, expected_sha: str) -> bool:
    try:
        return resolve_commit(root, f"refs/tags/{reference}") == expected_sha
    except portable.WorkflowError:
        return False


def explicit_previous_commit(root: Path, reference: str) -> str:
    version = portable.parse_semver(reference[1:]) if reference.startswith("v") else None
    if version is not None and not version[3] and not version[4] and version[0] >= 1:
        try:
            return resolve_commit(root, f"refs/tags/{reference}")
        except portable.WorkflowError as exc:
            raise portable.WorkflowError(
                "explicit previous release boundary must be an exact local tag"
            ) from exc
    if re.fullmatch(r"[0-9a-fA-F]{40}", reference) is not None:
        try:
            resolved = resolve_commit(root, reference)
        except portable.WorkflowError as exc:
            raise portable.WorkflowError(
                "explicit previous release boundary must be an exact local commit"
            ) from exc
        if resolved.lower() != reference.lower():
            raise portable.WorkflowError(
                "explicit previous release boundary must resolve to the exact commit SHA"
            )
        return resolved
    raise portable.WorkflowError(
        "explicit previous release boundary must be a stable SemVer tag at or above v1.0.0 "
        "or a full 40-hex commit SHA"
    )


def commit_details(root: Path, sha: str) -> dict[str, Any]:
    short_sha = str(portable.git_read(root, "rev-parse", "--short=7", sha)).strip()
    raw = str(
        portable.git_read(
            root,
            "show",
            "-s",
            "--format=%aE%x00%aN%x00%s%x00%B%x00%P",
            sha,
        )
    )
    if len(raw.encode()) > portable.MAX_BYTES:
        raise portable.WorkflowError(f"Git metadata for commit {sha} exceeds the size limit")
    parts = raw.rstrip("\n").split("\0")
    if len(parts) != COMMIT_METADATA_FIELDS:
        raise portable.WorkflowError(f"unexpected Git metadata for commit {sha}")
    author_email, author_name, subject, body, parents = parts
    return {
        "sha": sha,
        "short_sha": short_sha,
        "author": {"email": author_email, "name": author_name},
        "subject": subject,
        "body": body,
        "parent_count": len(parents.split()) if parents else 0,
    }


def collection_error(scope: str, message: str, **context: object) -> dict[str, Any]:
    return {"scope": scope, **context, "message": portable.redact(message)}


def paginated_items(
    hostname: str, path: str, scope: str, **context: object
) -> tuple[list[object], list[dict[str, Any]], bool]:
    try:
        result = portable.paginated(hostname, path)
    except portable.WorkflowError as exc:
        return [], [collection_error(scope, str(exc), **context)], False
    raw_items = result.get("items")
    raw_errors = result.get("errors")
    if not isinstance(raw_items, list) or not isinstance(raw_errors, list):
        return (
            [],
            [collection_error(scope, "GitLab pagination response is invalid", **context)],
            False,
        )
    errors = [collection_error(scope, str(message), **context) for message in raw_errors]
    return raw_items, errors, result.get("complete") is True and not errors


def gitlab_object(
    hostname: str, path: str, scope: str, **context: object
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    try:
        value = portable.glab_json(hostname, path)
    except portable.WorkflowError as exc:
        return None, [collection_error(scope, str(exc), **context)]
    if not isinstance(value, dict):
        return None, [collection_error(scope, "GitLab response is not an object", **context)]
    return value, []


def valid_iid(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


def normalized_user(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    username = value.get("username")
    if not isinstance(username, str) or not username:
        return None
    return {
        key: value.get(key)
        for key in ("id", "username", "name", "email", "public_email", "bot", "user_type")
    }


def confirmed_bot(user: dict[str, Any]) -> bool:
    return user.get("bot") is True or user.get("user_type") in {"project_bot", "service_account"}


def note_id(note: dict[str, Any]) -> tuple[int, int | str] | None:
    value = note.get("id")
    if isinstance(value, int) and not isinstance(value, bool):
        return 0, value
    if isinstance(value, str) and value:
        return 1, value
    return None


def normalize_notes(
    values: list[object], iid: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    notes: dict[tuple[int, int | str], dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        if not isinstance(value, dict) or note_id(value) is None:
            errors.append(
                collection_error(
                    "component_mr_notes_format",
                    "note entry has no stable ID",
                    iid=iid,
                    entry_index=index,
                )
            )
            continue
        notes.setdefault(cast("tuple[int, int | str]", note_id(value)), value)
    return [notes[key] for key in sorted(notes)], errors


def collect_component_merge_request(
    hostname: str, project_id: int, fallback: dict[str, Any]
) -> tuple[int, dict[str, Any], list[dict[str, Any]], bool]:
    iid = cast("int", fallback["iid"])
    base = f"projects/{project_id}/merge_requests/{iid}"
    errors: list[dict[str, Any]] = []
    details, detail_errors = gitlab_object(hostname, base, "component_mr_api", iid=iid)
    errors.extend(detail_errors)
    if details is None or valid_iid(details.get("iid")) != iid:
        if details is not None:
            errors.append(collection_error("component_mr_format", "MR IID does not match", iid=iid))
        details = dict(fallback)

    approvals, approval_errors = gitlab_object(
        hostname, f"{base}/approvals", "component_mr_approvals_api", iid=iid
    )
    errors.extend(approval_errors)
    approved_by: list[dict[str, Any]] = []
    if approvals is not None:
        raw_approved = approvals.get("approved_by")
        if not isinstance(raw_approved, list):
            errors.append(
                collection_error(
                    "component_mr_approvals_format", "approved_by is not an array", iid=iid
                )
            )
        else:
            for entry in raw_approved:
                user = normalized_user(entry.get("user") if isinstance(entry, dict) else None)
                if user is None:
                    errors.append(
                        collection_error(
                            "component_mr_approvals_format",
                            "approval has no identifiable user",
                            iid=iid,
                        )
                    )
                else:
                    approved_by.append(user)
    approved_by.sort(key=lambda user: cast("str", user["username"]).casefold())

    raw_discussions, discussion_errors, discussions_complete = paginated_items(
        hostname, f"{base}/discussions", "component_mr_discussions_api", iid=iid
    )
    errors.extend(discussion_errors)
    discussions: list[dict[str, Any]] = []
    discussion_notes: list[object] = []
    for index, discussion in enumerate(raw_discussions):
        if not isinstance(discussion, dict) or not isinstance(discussion.get("notes"), list):
            errors.append(
                collection_error(
                    "component_mr_discussions_format",
                    "discussion entry has no notes array",
                    iid=iid,
                    entry_index=index,
                )
            )
            continue
        discussions.append(discussion)
        discussion_notes.extend(cast("list[object]", discussion["notes"]))
    discussions.sort(key=lambda item: str(item.get("id", "")))

    standalone, standalone_errors, notes_complete = paginated_items(
        hostname, f"{base}/notes", "component_mr_notes_api", iid=iid
    )
    errors.extend(standalone_errors)
    notes, note_errors = normalize_notes([*discussion_notes, *standalone], iid)
    errors.extend(note_errors)

    closes, closes_errors, closes_complete = paginated_items(
        hostname, f"{base}/closes_issues", "component_mr_closes_issues_api", iid=iid
    )
    errors.extend(closes_errors)
    closes_issues: list[dict[str, Any]] = []
    for index, item in enumerate(closes):
        if (
            not isinstance(item, dict)
            or valid_iid(item.get("iid")) is None
            or ("project_id" in item and valid_iid(item.get("project_id")) is None)
        ):
            errors.append(
                collection_error(
                    "component_mr_closes_issues_format",
                    "closing issue entry has no positive IID",
                    iid=iid,
                    entry_index=index,
                )
            )
            closes_complete = False
            continue
        closes_issues.append(item)
    closes_issues.sort(key=lambda item: valid_iid(item.get("iid")) or 0)

    pipelines, pipeline_errors, pipelines_complete = paginated_items(
        hostname, f"{base}/pipelines", "component_mr_pipelines_api", iid=iid
    )
    errors.extend(pipeline_errors)
    pipeline_items: list[dict[str, Any]] = []
    diff_refs = details.get("diff_refs")
    pipeline_head_sha = diff_refs.get("head_sha") if isinstance(diff_refs, dict) else None
    if not isinstance(pipeline_head_sha, str) or not pipeline_head_sha:
        errors.append(
            collection_error(
                "component_mr_pipelines_format",
                "component MR has no exact pipeline head SHA",
                iid=iid,
            )
        )
        pipelines_complete = False
    for index, item in enumerate(pipelines):
        if not isinstance(item, dict):
            errors.append(
                collection_error(
                    "component_mr_pipelines_format",
                    "pipeline entry is not an object",
                    iid=iid,
                    entry_index=index,
                )
            )
            pipelines_complete = False
            continue
        if item.get("sha") == pipeline_head_sha:
            pipeline_items.append(item)
    pipeline_items.sort(key=lambda item: int(item.get("id", 0)))
    details.update(
        {
            "approved_by": approved_by,
            "discussions": discussions,
            "notes": notes,
            "closes_issues": closes_issues,
            "pipelines": pipeline_items,
            "pipeline_head_sha": pipeline_head_sha,
            "collection_complete": not errors
            and discussions_complete
            and notes_complete
            and closes_complete
            and pipelines_complete,
        }
    )
    return iid, details, errors, not errors


def noreply_username(email: str) -> str | None:
    local, separator, domain = email.casefold().partition("@")
    if not separator or not domain.startswith("users.noreply.gitlab"):
        return None
    match = re.fullmatch(r"(?:[0-9]+-)?([a-z0-9][a-z0-9_.-]*)", local)
    return match.group(1) if match else None


def verified_users(merge_requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    users: dict[str, dict[str, Any]] = {}
    for merge_request in merge_requests:
        values: list[object] = [merge_request.get("author")]
        values.extend(cast("list[object]", merge_request.get("approved_by", [])))
        values.extend(
            note.get("author")
            for note in cast("list[dict[str, Any]]", merge_request.get("notes", []))
        )
        for value in values:
            user = normalized_user(value)
            if user is not None:
                users.setdefault(cast("str", user["username"]).casefold(), user)
    return [users[key] for key in sorted(users)]


def contributor_candidates(
    commits: list[dict[str, Any]], merge_requests: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    users = verified_users(merge_requests)
    by_email: dict[str, dict[str, Any]] = {}
    for user in users:
        for field in ("email", "public_email"):
            email = user.get(field)
            if isinstance(email, str) and email:
                by_email[email.casefold()] = user
    candidates: dict[str, dict[str, Any]] = {}
    for commit in commits:
        if commit["parent_count"] > 1:
            continue
        author = cast("dict[str, str]", commit["author"])
        email = author["email"]
        matched_user = by_email.get(email.casefold())
        username = cast(
            "str | None",
            matched_user.get("username") if matched_user else noreply_username(email),
        )
        key = f"user:{username.casefold()}" if username else f"author:{author['name'].casefold()}"
        candidate = candidates.setdefault(
            key,
            {
                "display": f"@{username}" if username else author["name"],
                "username": username,
                "name": author["name"],
                "email": email,
                "commit_shas": [],
                "username_evidence": "gitlab_user_email"
                if matched_user
                else "gitlab_noreply"
                if username
                else None,
            },
        )
        cast("list[str]", candidate["commit_shas"]).append(cast("str", commit["sha"]))
    return [candidates[key] for key in sorted(candidates)]


def reviewer_candidates(merge_requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for merge_request in merge_requests:
        iid = cast("int", merge_request["iid"])
        author = normalized_user(merge_request.get("author"))
        author_username = cast("str", author["username"]).casefold() if author else None
        for user in cast("list[dict[str, Any]]", merge_request.get("approved_by", [])):
            if confirmed_bot(user):
                continue
            username = cast("str", user["username"])
            item = evidence.setdefault(
                username.casefold(),
                {"username": username, "name": user.get("name"), "evidence": []},
            )
            cast("list[dict[str, Any]]", item["evidence"]).append(
                {"kind": "approval", "merge_request_iid": iid}
            )
        for note in cast("list[dict[str, Any]]", merge_request.get("notes", [])):
            if note.get("system") is True:
                continue
            comment_user = normalized_user(note.get("author"))
            if comment_user is None or confirmed_bot(comment_user):
                continue
            username = cast("str", comment_user["username"])
            own_comment = username.casefold() == author_username
            item = evidence.setdefault(
                username.casefold(),
                {"username": username, "name": comment_user.get("name"), "evidence": []},
            )
            cast("list[dict[str, Any]]", item["evidence"]).append(
                {"kind": "comment", "merge_request_iid": iid, "own_merge_request": own_comment}
            )
    reviewers = []
    for key in sorted(evidence):
        item = evidence[key]
        item["evidence"] = sorted(
            cast("list[dict[str, Any]]", item["evidence"]),
            key=lambda value: (cast("int", value["merge_request_iid"]), cast("str", value["kind"])),
        )
        if any(
            value["kind"] == "approval" or value.get("own_merge_request") is False
            for value in cast("list[dict[str, Any]]", item["evidence"])
        ):
            reviewers.append(item)
    return reviewers


def milestone_candidates(
    release_mr: dict[str, Any],
    merge_requests: list[dict[str, Any]],
    active: list[object],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: dict[tuple[int, int | str], dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []

    def add(value: object, source: dict[str, Any]) -> None:
        if value is None:
            return
        if not isinstance(value, dict):
            errors.append(
                collection_error("milestone_format", "milestone is not an object", **source)
            )
            return
        milestone_id = valid_iid(value.get("id"))
        title = value.get("title")
        if milestone_id is None and (not isinstance(title, str) or not title):
            errors.append(
                collection_error("milestone_format", "milestone has no identity", **source)
            )
            return
        key: tuple[int, int | str] = (0, milestone_id) if milestone_id else (1, cast("str", title))
        item = candidates.setdefault(
            key,
            {
                "id": milestone_id,
                "iid": valid_iid(value.get("iid")),
                "title": title,
                "state": value.get("state"),
                "due_date": value.get("due_date"),
                "web_url": value.get("web_url"),
                "provenance": [],
            },
        )
        provenance = cast("list[dict[str, Any]]", item["provenance"])
        if source not in provenance:
            provenance.append(source)

    add(release_mr.get("milestone"), {"source": "release_merge_request"})
    for merge_request in merge_requests:
        add(
            merge_request.get("milestone"),
            {"source": "component_merge_request", "merge_request_iid": merge_request["iid"]},
        )
    for value in active:
        add(value, {"source": "project_milestone"})
    for item in candidates.values():
        cast("list[dict[str, Any]]", item["provenance"]).sort(
            key=lambda value: (str(value["source"]), int(value.get("merge_request_iid", 0)))
        )
    return [candidates[key] for key in sorted(candidates)], errors


def linked_issue_iids(text: str, hostname: str, project_path: str) -> list[int]:
    escaped_host = re.escape(hostname.casefold())
    escaped_project = re.escape(project_path.casefold())
    lowered = text.casefold()
    values = {
        int(match)
        for pattern in (
            r"(?<![\w/])#([1-9][0-9]*)",
            rf"(?<![\w/]){escaped_project}#([1-9][0-9]*)",
            rf"https://{escaped_host}/{escaped_project}/-/(?:issues|work_items)/([1-9][0-9]*)",
        )
        for match in re.findall(pattern, lowered)
    }
    return sorted(values)


def collect_work_items(
    hostname: str,
    project_id: int,
    project_path: str,
    release_merge_request: dict[str, Any],
    merge_requests: list[dict[str, Any]],
    commits: list[dict[str, Any]],
    workers: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    provenance: dict[tuple[int, int], list[dict[str, Any]]] = {}

    def add(item_project_id: int, iid: int, source: dict[str, Any]) -> None:
        sources = provenance.setdefault((item_project_id, iid), [])
        if source not in sources:
            sources.append(source)

    release_iid = valid_iid(release_merge_request.get("iid"))
    if release_iid is None:
        raise portable.WorkflowError("release merge request IID is unavailable")
    for issue in cast("list[dict[str, Any]]", release_merge_request.get("closes_issues", [])):
        iid = valid_iid(issue.get("iid"))
        if iid is not None:
            issue_project_id = valid_iid(issue.get("project_id")) or project_id
            add(issue_project_id, iid, {"source": "release_merge_request_closes_issues"})
    release_text = (
        f"{release_merge_request.get('title') or ''}\n"
        f"{release_merge_request.get('description') or ''}"
    )
    for iid in linked_issue_iids(release_text, hostname, project_path):
        add(project_id, iid, {"source": "release_merge_request_text"})

    for merge_request in merge_requests:
        mr_iid = cast("int", merge_request["iid"])
        for issue in cast("list[dict[str, Any]]", merge_request.get("closes_issues", [])):
            iid = valid_iid(issue.get("iid"))
            if iid is not None:
                issue_project_id = valid_iid(issue.get("project_id")) or project_id
                add(
                    issue_project_id,
                    iid,
                    {"source": "closes_issues", "merge_request_iid": mr_iid},
                )
        text = f"{merge_request.get('title') or ''}\n{merge_request.get('description') or ''}"
        for iid in linked_issue_iids(text, hostname, project_path):
            add(
                project_id,
                iid,
                {"source": "component_merge_request_text", "merge_request_iid": mr_iid},
            )
    for commit in commits:
        text = f"{commit['subject']}\n{commit['body']}"
        for iid in linked_issue_iids(text, hostname, project_path):
            add(project_id, iid, {"source": "commit_message", "commit_sha": commit["sha"]})

    errors: list[dict[str, Any]] = []
    seed_keys = sorted(provenance)
    if len(seed_keys) > MAX_WORK_ITEMS:
        errors.append(
            collection_error(
                "work_item_limit", f"work-item candidates exceed the limit of {MAX_WORK_ITEMS}"
            )
        )
        seed_keys = seed_keys[:MAX_WORK_ITEMS]
        provenance = {key: provenance[key] for key in seed_keys}

    def links(
        key: tuple[int, int],
    ) -> tuple[tuple[int, int], list[object], list[dict[str, Any]], bool]:
        item_project_id, iid = key
        items, item_errors, complete = paginated_items(
            hostname,
            f"projects/{item_project_id}/issues/{iid}/links",
            "work_item_links_api",
            project_id=item_project_id,
            iid=iid,
        )
        return key, items, item_errors, complete

    with ThreadPoolExecutor(
        max_workers=min(workers, len(seed_keys)) if seed_keys else 1,
        thread_name_prefix="release-work-item-links",
    ) as executor:
        link_results = list(executor.map(links, seed_keys))
    links_complete = True
    for source_key, values, item_errors, complete in link_results:
        source_project_id, source_iid = source_key
        errors.extend(item_errors)
        links_complete = links_complete and complete
        for value in values:
            iid = valid_iid(value.get("iid")) if isinstance(value, dict) else None
            linked_project_id = (
                valid_iid(value.get("project_id")) if isinstance(value, dict) else None
            )
            if iid is None:
                errors.append(
                    collection_error(
                        "work_item_links_format", "linked work item has no IID", iid=source_iid
                    )
                )
                continue
            linked_key = (linked_project_id or source_project_id, iid)
            if linked_key not in provenance and len(provenance) >= MAX_WORK_ITEMS:
                errors.append(
                    collection_error(
                        "work_item_limit",
                        f"work-item candidates exceed the limit of {MAX_WORK_ITEMS}",
                    )
                )
                links_complete = False
                continue
            add(
                linked_key[0],
                iid,
                {
                    "source": "issue_link",
                    "source_project_id": source_project_id,
                    "source_iid": source_iid,
                    "depth": 1,
                },
            )

    def details(
        key: tuple[int, int],
    ) -> tuple[tuple[int, int], dict[str, Any] | None, list[dict[str, Any]]]:
        item_project_id, iid = key
        value, item_errors = gitlab_object(
            hostname,
            f"projects/{item_project_id}/issues/{iid}",
            "work_item_api",
            project_id=item_project_id,
            iid=iid,
        )
        if value is not None and valid_iid(value.get("iid")) != iid:
            item_errors.append(
                collection_error("work_item_format", "issue IID does not match", iid=iid)
            )
            value = None
        return key, value, item_errors

    all_keys = sorted(provenance)
    with ThreadPoolExecutor(
        max_workers=min(workers, len(all_keys)) if all_keys else 1,
        thread_name_prefix="release-work-items",
    ) as executor:
        detail_results = list(executor.map(details, all_keys))
    candidates: list[dict[str, Any]] = []
    for key, value, item_errors in detail_results:
        item_project_id, iid = key
        errors.extend(item_errors)
        sources = sorted(
            provenance[key],
            key=lambda item: (
                str(item["source"]),
                int(item.get("merge_request_iid", 0)),
                str(item.get("commit_sha", "")),
                int(item.get("source_iid", 0)),
            ),
        )
        candidates.append(
            {
                "project_id": item_project_id,
                "iid": iid,
                "details": value,
                "provenance": sources,
            }
        )
    return candidates, errors, links_complete and not errors


def normalized_merge_requests(
    values: list[object], target_branch: str, sha: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_iid: dict[int, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            errors.append(
                {
                    "scope": "commit_merge_requests_format",
                    "sha": sha,
                    "entry_index": index,
                    "message": "merge request entry is not an object",
                }
            )
            continue
        iid = value.get("iid")
        if not isinstance(iid, int) or isinstance(iid, bool):
            errors.append(
                {
                    "scope": "commit_merge_requests_format",
                    "sha": sha,
                    "entry_index": index,
                    "message": "merge request entry has no integer IID",
                }
            )
            continue
        if value.get("state") != "merged" or value.get("target_branch") != target_branch:
            continue
        by_iid.setdefault(iid, {field: value.get(field) for field in MR_FIELDS})
    return [by_iid[iid] for iid in sorted(by_iid)], errors


def commit_associations(
    hostname: str, project_id: int, target_branch: str, sha: str
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], bool]:
    result = portable.paginated(
        hostname,
        f"projects/{project_id}/repository/commits/{urlquote(sha, safe='')}/merge_requests",
    )
    errors = [
        {
            "scope": "commit_merge_requests_api",
            "sha": sha,
            "message": portable.redact(message),
        }
        for message in cast("list[str]", result["errors"])
    ]
    merge_requests, format_errors = normalized_merge_requests(
        cast("list[object]", result["items"]), target_branch, sha
    )
    errors.extend(format_errors)
    complete = bool(result["complete"]) and not format_errors
    return sha, merge_requests, errors, complete


def previous_tag_metadata(hostname: str, project_id: int, reference: str) -> dict[str, Any]:
    value = portable.glab_json(
        hostname,
        f"projects/{project_id}/repository/tags/{urlquote(reference, safe='')}",
    )
    if not isinstance(value, dict):
        raise portable.WorkflowError("GitLab tag response is not an object")
    tag_created_at = value.get("created_at")
    commit = value.get("commit")
    commit_created_at = commit.get("created_at") if isinstance(commit, dict) else None
    effective = tag_created_at or commit_created_at
    source = (
        "tag.created_at"
        if tag_created_at
        else "commit.created_at proxy"
        if commit_created_at
        else None
    )
    return {
        "name": value.get("name"),
        "tag_created_at": tag_created_at,
        "commit_created_at": commit_created_at,
        "effective_created_at": effective,
        "effective_created_at_source": source,
    }


def evidence_context(
    evidence_value: str | Path,
) -> tuple[Path, dict[str, Any], Path, str]:
    source = portable.regular_file(Path(evidence_value), "release MR evidence")
    _, evidence = portable.artifact_payload(source, "evidence_snapshot")
    if evidence.get("profile") != "release-prepare":
        raise portable.WorkflowError("release inventory requires release-prepare evidence")
    root = portable.artifact_root(Path(str(evidence.get("artifact_root", ""))))
    evidence_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    expected = root / "artifacts" / "evidence_snapshot" / f"{evidence_digest}.json"
    if source != expected:
        raise portable.WorkflowError("release MR evidence is not content-addressed")
    return source, evidence, root, evidence_digest


def collect_inventory(
    evidence: dict[str, Any],
    evidence_digest: str,
    repo_root: str,
    previous_ref: str | None,
    workers: int,
) -> dict[str, Any]:
    if not 1 <= workers <= MAX_WORKERS:
        raise portable.WorkflowError(f"workers must be between 1 and {MAX_WORKERS}")
    root = repository_root(repo_root)
    project = evidence.get("project")
    object_value = evidence.get("object")
    target = evidence.get("target")
    head_sha = evidence.get("head_sha")
    if (
        not isinstance(project, dict)
        or not isinstance(project.get("id"), int)
        or not isinstance(object_value, dict)
        or not isinstance(target, dict)
        or not isinstance(head_sha, str)
        or not head_sha
    ):
        raise portable.WorkflowError("release MR evidence identity is incomplete")
    hostname = project.get("hostname")
    project_path = project.get("path_with_namespace")
    component_target_branch = object_value.get("source_branch")
    if (
        not isinstance(hostname, str)
        or not isinstance(project_path, str)
        or not project_path
        or not isinstance(component_target_branch, str)
    ):
        raise portable.WorkflowError(
            "release MR host, project path, or source branch is unavailable"
        )
    if resolve_commit(root, head_sha).lower() != head_sha.lower():
        raise portable.WorkflowError("local checkout does not resolve the exact release head")

    previous_ref_explicit = previous_ref is not None
    selected_previous_ref = (
        previous_ref if previous_ref_explicit else first_parent_tag(root, head_sha)
    )
    if previous_ref_explicit:
        previous_sha = explicit_previous_commit(root, cast("str", selected_previous_ref))
    elif selected_previous_ref is not None:
        previous_sha = resolve_commit(root, f"refs/tags/{selected_previous_ref}")
    else:
        previous_sha = None
    if previous_sha is not None:
        try:
            portable.git_read(root, "merge-base", "--is-ancestor", previous_sha, head_sha)
        except portable.WorkflowError as exc:
            raise portable.WorkflowError("previous release boundary is not an ancestor") from exc
    revision_range = f"{previous_sha}..{head_sha}" if previous_sha else head_sha
    commit_output = str(portable.git_read(root, "rev-list", "--reverse", revision_range))
    if len(commit_output.encode()) > portable.MAX_BYTES:
        raise portable.WorkflowError("release commit range exceeds the size limit")
    commit_shas = [line for line in commit_output.splitlines() if line]
    if len(commit_shas) > MAX_RELEASE_COMMITS:
        raise portable.WorkflowError("release commit range exceeds the protective limit")
    commit_records = [commit_details(root, sha) for sha in commit_shas]

    association_args = [
        (hostname, project["id"], component_target_branch, sha) for sha in commit_shas
    ]
    with ThreadPoolExecutor(
        max_workers=min(workers, len(commit_shas)) if commit_shas else 1,
        thread_name_prefix="release-inventory",
    ) as executor:
        associations = list(executor.map(lambda args: commit_associations(*args), association_args))

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    merge_requests_by_iid: dict[int, dict[str, Any]] = {}
    association_by_sha = {
        sha: (mrs, item_errors, complete) for sha, mrs, item_errors, complete in associations
    }
    for commit in commit_records:
        merge_requests, item_errors, associations_complete = association_by_sha[commit["sha"]]
        errors.extend(item_errors)
        for merge_request in merge_requests:
            merge_requests_by_iid.setdefault(cast("int", merge_request["iid"]), merge_request)
        commit.update(
            {
                "merge_requests": merge_requests,
                "merge_requests_complete": associations_complete,
                "direct": associations_complete
                and not merge_requests
                and commit["parent_count"] <= 1,
                "technical_candidate": bool(TECHNICAL_SUBJECT_RE.search(commit["subject"])),
            }
        )
    if evidence.get("retrieval_complete") is not True:
        errors.append(
            {
                "scope": "release_mr_evidence",
                "message": "release MR evidence collection is incomplete",
            }
        )

    if len(merge_requests_by_iid) > MAX_COMPONENT_MRS:
        errors.append(
            collection_error(
                "component_mr_limit",
                f"component merge requests exceed the limit of {MAX_COMPONENT_MRS}",
            )
        )
        merge_requests_by_iid = {
            iid: merge_requests_by_iid[iid]
            for iid in sorted(merge_requests_by_iid)[:MAX_COMPONENT_MRS]
        }

    component_values = [merge_requests_by_iid[iid] for iid in sorted(merge_requests_by_iid)]
    component_args = [(hostname, project["id"], value) for value in component_values]
    with ThreadPoolExecutor(
        max_workers=min(workers, len(component_args)) if component_args else 1,
        thread_name_prefix="release-component-mrs",
    ) as executor:
        component_results = list(
            executor.map(lambda args: collect_component_merge_request(*args), component_args)
        )
    collected_merge_requests: dict[int, dict[str, Any]] = {}
    for iid, merge_request, item_errors, _complete in component_results:
        collected_merge_requests[iid] = merge_request
        errors.extend(item_errors)

    previous_tag = None
    if (
        selected_previous_ref
        and previous_sha
        and exact_local_tag(root, selected_previous_ref, previous_sha)
    ):
        try:
            previous_tag = previous_tag_metadata(hostname, project["id"], selected_previous_ref)
            if previous_tag["effective_created_at"] is None:
                warnings.append(
                    {
                        "scope": "previous_tag_format",
                        "message": "tag and commit creation timestamps are unavailable",
                    }
                )
        except portable.WorkflowError as exc:
            warnings.append({"scope": "previous_tag_api", "message": portable.redact(str(exc))})

    merge_requests = [collected_merge_requests[iid] for iid in sorted(collected_merge_requests)]
    direct_commits = [commit for commit in commit_records if commit["direct"]]
    contributors = contributor_candidates(commit_records, merge_requests)
    reviewers = reviewer_candidates(merge_requests)

    project_milestones, project_milestone_errors, project_milestones_complete = paginated_items(
        hostname,
        f"projects/{project['id']}/milestones?include_parent_milestones=true",
        "project_milestones_api",
    )
    errors.extend(project_milestone_errors)
    milestones, milestone_errors = milestone_candidates(
        object_value, merge_requests, project_milestones
    )
    errors.extend(milestone_errors)

    release_iid = valid_iid(object_value.get("iid"))
    if release_iid is None:
        raise portable.WorkflowError("release merge request IID is unavailable")
    release_closes, release_closes_errors, release_closes_complete = paginated_items(
        hostname,
        f"projects/{project['id']}/merge_requests/{release_iid}/closes_issues",
        "release_mr_closes_issues_api",
        iid=release_iid,
    )
    errors.extend(release_closes_errors)
    release_closes_issues: list[dict[str, Any]] = []
    for index, item in enumerate(release_closes):
        if (
            not isinstance(item, dict)
            or valid_iid(item.get("iid")) is None
            or ("project_id" in item and valid_iid(item.get("project_id")) is None)
        ):
            errors.append(
                collection_error(
                    "release_mr_closes_issues_format",
                    "closing issue entry has no positive IID",
                    iid=release_iid,
                    entry_index=index,
                )
            )
            release_closes_complete = False
            continue
        release_closes_issues.append(item)

    work_items, work_item_errors, work_items_complete = collect_work_items(
        hostname,
        project["id"],
        project_path,
        {
            **object_value,
            "closes_issues": release_closes_issues,
        },
        merge_requests,
        commit_records,
        workers,
    )
    errors.extend(work_item_errors)
    artifact_root_value = str(evidence["artifact_root"])
    collection_completeness = {
        "component_merge_requests": all(
            merge_request["collection_complete"] for merge_request in merge_requests
        ),
        "project_milestones": project_milestones_complete,
        "work_items": release_closes_complete and work_items_complete,
    }
    return {
        "schema_version": portable.ARTIFACT_VERSION,
        "profile": "release-prepare",
        "external_mutations": False,
        "evidence_digest": evidence_digest,
        "target": target,
        "repo_root": str(root),
        "project_id": project["id"],
        "hostname": hostname,
        "head_sha": head_sha,
        "component_target_branch": component_target_branch,
        "previous_ref": selected_previous_ref,
        "previous_ref_explicit": previous_ref_explicit,
        "previous_sha": previous_sha,
        "previous_tag": previous_tag,
        "revision_range": revision_range,
        "commits": commit_records,
        "merge_requests": merge_requests,
        "direct_commits": direct_commits,
        "contributors": contributors,
        "reviewers": reviewers,
        "milestone_candidates": milestones,
        "work_item_candidates": work_items,
        "collection_completeness": collection_completeness,
        "errors": errors,
        "warnings": warnings,
        "complete": not errors and all(collection_completeness.values()),
        "artifact_root": artifact_root_value,
        "prepared_at": datetime.now(UTC).isoformat(),
        "counts": {
            "commits": len(commit_records),
            "merge_requests": len(merge_requests),
            "direct_commits": len(direct_commits),
            "contributors": len(contributors),
            "reviewers": len(reviewers),
            "milestone_candidates": len(milestones),
            "work_item_candidates": len(work_items),
            "errors": len(errors),
            "warnings": len(warnings),
        },
    }


def prepare_inventory(
    evidence_value: str,
    repo_root: str,
    previous_ref: str | None,
    workers: int = DEFAULT_WORKERS,
) -> dict[str, object]:
    _, evidence, root, evidence_digest = evidence_context(evidence_value)
    inventory = collect_inventory(evidence, evidence_digest, repo_root, previous_ref, workers)
    path, inventory_digest = portable.write_artifact(root, "release_inventory", inventory)
    return {
        "status": "ok" if inventory["complete"] else "incomplete",
        "summary": {
            "tldr": "Prepared an exact tag-to-head release inventory.",
            "scope": [str(inventory["target"].get("url", ""))],
            "risks": ["inventory incomplete"] if not inventory["complete"] else [],
            "checks": [
                "exact release head",
                "first-parent release boundary",
                "paginated commit-to-MR associations",
                "direct commits",
            ],
        },
        "artifact_path": str(path),
        "digest": inventory_digest,
        "complete": inventory["complete"],
        "previous_ref": inventory["previous_ref"],
        "previous_sha": inventory["previous_sha"],
        "head_sha": inventory["head_sha"],
        "counts": inventory["counts"],
        "external_mutations": False,
    }


def validate_inventory_binding(
    inventory_value: str | Path, evidence_value: str | Path
) -> tuple[Path, dict[str, Any], str]:
    _, evidence, root, evidence_digest = evidence_context(evidence_value)
    path = portable.regular_file(Path(inventory_value), "release inventory")
    inventory_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = root / "artifacts" / "release_inventory" / f"{inventory_digest}.json"
    if path != expected:
        raise portable.WorkflowError("release inventory is not content-addressed")
    _, inventory = portable.artifact_payload(path, "release_inventory")
    if (
        inventory.get("evidence_digest") != evidence_digest
        or inventory.get("target") != evidence.get("target")
        or inventory.get("head_sha") != evidence.get("head_sha")
    ):
        raise portable.WorkflowError("release inventory does not bind the release MR evidence")
    return path, inventory, inventory_digest


def inventory_fingerprint(inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in inventory.items()
        if key not in {"artifact_root", "prepared_at"}
    }


def refresh_inventory(inventory: dict[str, Any], evidence_value: str | Path) -> dict[str, Any]:
    _, evidence, _, evidence_digest = evidence_context(evidence_value)
    previous_ref = inventory.get("previous_ref") if inventory.get("previous_ref_explicit") else None
    if previous_ref is not None and not isinstance(previous_ref, str):
        raise portable.WorkflowError("release inventory previous boundary is invalid")
    repo_root = inventory.get("repo_root")
    if not isinstance(repo_root, str):
        raise portable.WorkflowError("release inventory repository root is invalid")
    return collect_inventory(evidence, evidence_digest, repo_root, previous_ref, DEFAULT_WORKERS)
