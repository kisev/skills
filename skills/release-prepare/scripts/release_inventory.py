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
    try:
        value = str(
            portable.git_read(
                root,
                "describe",
                "--first-parent",
                "--tags",
                "--match",
                "v[0-9]*",
                "--abbrev=0",
                head_sha,
            )
        ).strip()
    except portable.WorkflowError:
        return None
    if (
        re.fullmatch(
            r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?",
            value,
        )
        is None
    ):
        raise portable.WorkflowError("nearest first-parent v* tag is not valid SemVer")
    return value


def exact_local_tag(root: Path, reference: str, expected_sha: str) -> bool:
    try:
        return resolve_commit(root, f"refs/tags/{reference}") == expected_sha
    except portable.WorkflowError:
        return False


def commit_details(root: Path, sha: str) -> dict[str, Any]:
    short_sha = str(portable.git_read(root, "rev-parse", "--short=7", sha)).strip()
    raw = str(
        portable.git_read(
            root,
            "show",
            "-s",
            "--format=%ae%x00%an%x00%s%x00%B%x00%P",
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
    component_target_branch = object_value.get("source_branch")
    if not isinstance(hostname, str) or not isinstance(component_target_branch, str):
        raise portable.WorkflowError("release MR host or source branch is unavailable")
    if resolve_commit(root, head_sha).lower() != head_sha.lower():
        raise portable.WorkflowError("local checkout does not resolve the exact release head")

    previous_ref_explicit = previous_ref is not None
    selected_previous_ref = previous_ref or first_parent_tag(root, head_sha)
    previous_sha = (
        resolve_commit(root, selected_previous_ref) if selected_previous_ref is not None else None
    )
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

    merge_requests = [merge_requests_by_iid[iid] for iid in sorted(merge_requests_by_iid)]
    direct_commits = [commit for commit in commit_records if commit["direct"]]
    artifact_root_value = str(evidence["artifact_root"])
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
        "errors": errors,
        "warnings": warnings,
        "complete": not errors,
        "artifact_root": artifact_root_value,
        "prepared_at": datetime.now(UTC).isoformat(),
        "counts": {
            "commits": len(commit_records),
            "merge_requests": len(merge_requests),
            "direct_commits": len(direct_commits),
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
