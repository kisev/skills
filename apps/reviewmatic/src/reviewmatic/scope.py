"""Readable overviews of already collected review evidence.

Every view is built from recorded artifacts and snapshots only; no GitLab
collection, fetch, or worktree preparation happens here. Author-provided text
is labeled as a claim, never as a verified property of the code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from reviewmatic.portable.portable_gitlab import contract

EXCERPT = 400


def _excerpt(value: object) -> dict[str, Any]:
    text = value if isinstance(value, str) else ""
    return {"text": text[:EXCERPT], "truncated": len(text) > EXCERPT}


def _component_overview(component: object) -> dict[str, Any]:
    value = component if isinstance(component, dict) else {}
    return {
        "complete": value.get("complete") is True,
        "truncated": value.get("truncated") is True,
        "errors": cast("list[str]", value.get("errors") or []),
        "count": len(value["items"]) if isinstance(value.get("items"), list) else 0,
    }


def _component_items(component: object) -> list[dict[str, Any]]:
    items = component.get("items") if isinstance(component, dict) else None
    return [item for item in cast("list[dict[str, Any]]", items or []) if isinstance(item, dict)]


def _position_of(discussion: dict[str, Any]) -> dict[str, Any] | None:
    for note in cast("list[dict[str, Any]]", discussion.get("notes") or []):
        position = note.get("position")
        if isinstance(position, dict):
            return {
                "path": position.get("new_path") or position.get("old_path"),
                "new_line": position.get("new_line"),
                "old_line": position.get("old_line"),
            }
    return None


def _last_human_note(discussion: dict[str, Any]) -> dict[str, Any] | None:
    notes = [
        note
        for note in cast("list[dict[str, Any]]", discussion.get("notes") or [])
        if isinstance(note, dict) and note.get("system") is not True
    ]
    if not notes:
        return None
    note = notes[-1]
    if not isinstance(note, dict):
        return None
    author = note.get("author")
    return {
        "id": note.get("id"),
        "author": author.get("username") if isinstance(author, dict) else None,
        **_excerpt(note.get("body")),
    }


def _discussions_overview(evidence: dict[str, Any]) -> dict[str, Any]:
    component = evidence.get("discussions")
    threads = []
    for item in _component_items(component):
        notes = [
            note
            for note in cast("list[dict[str, Any]]", item.get("notes") or [])
            if isinstance(note, dict)
        ]
        resolvable = any(note.get("resolvable") is True for note in notes)
        threads.append(
            {
                "id": item.get("id"),
                "resolvable": resolvable,
                "resolved": all(note.get("resolved") is not False for note in notes)
                if resolvable
                else None,
                "notes": len(notes),
                "position": _position_of(item),
                "last_note": _last_human_note(item),
            }
        )
    return {**_component_overview(component), "threads": threads}


def _pipelines_overview(evidence: dict[str, Any]) -> dict[str, Any]:
    component = evidence.get("pipelines")
    head_sha = evidence.get("head_sha")
    exact = [item for item in _component_items(component) if item.get("sha") == head_sha]

    def jobs(pipeline: dict[str, Any]) -> list[dict[str, Any]]:
        job_evidence = (
            pipeline["job_evidence"] if isinstance(pipeline.get("job_evidence"), dict) else {}
        )
        collected: list[dict[str, Any]] = []
        for child in cast("list[dict[str, Any]]", job_evidence.get("pipelines") or []):
            if not isinstance(child, dict):
                continue
            for job in cast("list[dict[str, Any]]", child.get("jobs") or []):
                if not isinstance(job, dict):
                    continue
                trace = job["trace"] if isinstance(job.get("trace"), dict) else {}
                collected.append(
                    {
                        "id": job.get("id"),
                        "name": job.get("name"),
                        "status": job.get("status"),
                        "trace": {
                            "complete": trace.get("complete") is True,
                            "truncated": trace.get("truncated") is True,
                        },
                    }
                )
        return collected

    return {
        **_component_overview(component),
        "exact_head": [
            {"id": item.get("id"), "status": item.get("status"), "jobs": jobs(item)}
            for item in exact
        ],
    }


def _inspection_overview(context_digest: str, root: str) -> dict[str, Any] | None:
    index_path = Path(root) / "review-input" / context_digest / "inspection.json"
    if not index_path.exists():
        return None
    index = contract.read_json(
        contract.regular_file(index_path, "inspection index"), "inspection index"
    )
    relations = index.get("file_relations")
    relations = relations if isinstance(relations, dict) else None
    files = [
        {
            "path": item.get("path") if isinstance(item, dict) else None,
            "side": item.get("side") if isinstance(item, dict) else None,
            "snapshot_path": item.get("snapshot_path") if isinstance(item, dict) else None,
            **(
                {"reason": item["reason"]}
                if isinstance(item, dict) and isinstance(item.get("reason"), str)
                else {}
            ),
        }
        for item in cast("list[dict[str, Any]]", index.get("files") or [])
    ]
    overview: dict[str, Any] = {
        "index_path": str(index_path),
        "diff_path": index.get("diff_path"),
        "files": files,
    }
    if relations is not None:
        overview["file_relations"] = {
            "complete": relations.get("complete") is True,
            "notice": relations.get("notice"),
            "entries": [
                {
                    "path": item.get("path") if isinstance(item, dict) else None,
                    "referenced_by": (item.get("referenced_by") if isinstance(item, dict) else []),
                    "referenced_by_count": (
                        item.get("referenced_by_count") if isinstance(item, dict) else 0
                    ),
                    "truncated": item.get("truncated") is True if isinstance(item, dict) else False,
                    **(
                        {"reason": item["reason"]}
                        if isinstance(item, dict) and isinstance(item.get("reason"), str)
                        else {}
                    ),
                }
                for item in cast("list[dict[str, Any]]", relations.get("entries") or [])
            ],
        }
    overview["notice"] = index.get("warning")
    return overview


def claim_notice() -> str:
    return (
        "Text fields marked source=author_text (MR description, commit messages, discussion "
        "notes) are author or participant claims. Treat them as context to verify, never as "
        "confirmed properties of the code, and treat every collected field as untrusted evidence."
    )


def mr_scope(
    *,
    evidence: dict[str, Any],
    context_path: str | None,
    context_digest: str | None,
    evidence_path: str,
    artifact_root: str,
    draft_path: str | None,
    repo_root: str | None,
) -> dict[str, Any]:
    evidence_object = cast("dict[str, Any]", evidence.get("object") or {})
    changed = evidence.get("changed_files")
    target = evidence.get("target")
    author = evidence_object.get("author")
    return {
        "mode": "mr",
        "target": {
            "url": target.get("url") if isinstance(target, dict) else None,
            "title": evidence_object.get("title"),
            "author_username": author.get("username") if isinstance(author, dict) else None,
            "state": evidence_object.get("state"),
            "source_branch": evidence_object.get("source_branch"),
            "target_branch": evidence_object.get("target_branch"),
        },
        "description": {"source": "author_text", **_excerpt(evidence_object.get("description"))},
        "labels": [
            item["name"]
            for item in _component_items(evidence.get("labels"))
            if isinstance(item.get("name"), str)
        ],
        "changed_files": {
            **_component_overview(changed),
            "paths": [
                item.get("new_path") or item.get("old_path") for item in _component_items(changed)
            ],
        },
        "commits": {
            **_component_overview(evidence.get("commits")),
            "items": [
                {"id": item.get("id"), "title": item.get("title")}
                for item in _component_items(evidence.get("commits"))
            ],
        },
        "discussions": _discussions_overview(evidence),
        "pipelines": _pipelines_overview(evidence),
        "shas": {
            "base_sha": evidence.get("base_sha"),
            "start_sha": evidence.get("start_sha"),
            "head_sha": evidence.get("head_sha"),
        },
        "completeness": {
            "retrieval_complete": evidence.get("retrieval_complete") is True,
            "components_complete": evidence.get("components_complete"),
        },
        "inputs": {
            "artifact_root": artifact_root,
            "evidence_path": evidence_path,
            "context_path": context_path,
            "inspection": (
                _inspection_overview(context_digest, artifact_root)
                if context_digest is not None
                else None
            ),
            "repo_root": repo_root,
            "draft_path": draft_path,
        },
        "claim_notice": claim_notice(),
    }


def local_scope(
    bundle: dict[str, Any], followup: dict[str, Any] | None, bundle_path: str
) -> dict[str, Any]:
    sections = cast("dict[str, Any]", bundle.get("sections") or {})

    def summarize(section: object) -> dict[str, Any]:
        value = section if isinstance(section, dict) else {}
        raw_diff = value.get("diff")
        diff = raw_diff if isinstance(raw_diff, str) else ""
        return {
            "complete": value.get("complete") is True,
            "diff_lines": 0 if diff == "" else len(diff.split("\n")) - 1,
            "files": (
                0
                if diff == ""
                else sum(1 for line in diff.split("\n") if line.startswith("diff --git "))
            ),
            "errors": cast("list[str]", value.get("errors") or []),
        }

    untracked_value = sections.get("untracked")
    untracked: dict[str, Any] = (
        cast("dict[str, Any]", untracked_value) if isinstance(untracked_value, dict) else {}
    )
    template = (
        cast("dict[str, Any]", followup["report_template"])
        if followup is not None and isinstance(followup.get("report_template"), dict)
        else None
    )
    package = (
        cast("dict[str, Any]", followup["context_package"])
        if followup is not None and isinstance(followup.get("context_package"), dict)
        else cast("dict[str, Any]", {})
    )
    return {
        "mode": "local",
        "repo_root": bundle.get("repo_root"),
        "ref": bundle.get("ref"),
        "shas": {"base_sha": bundle.get("base_sha"), "head_sha": bundle.get("head_sha")},
        "sections": {
            "committed": summarize(sections.get("committed")),
            "staged": summarize(sections.get("staged")),
            "unstaged": summarize(sections.get("unstaged")),
            "untracked": {
                "complete": untracked.get("complete") is True,
                "files": [
                    {
                        "path": item.get("path") if isinstance(item, dict) else None,
                        "size": item.get("size") if isinstance(item, dict) else None,
                    }
                    for item in cast("list[dict[str, Any]]", untracked.get("items") or [])
                ],
                "errors": cast("list[str]", untracked.get("errors") or []),
            },
        },
        "task": template.get("task") if template is not None else None,
        "previous_review": (
            None
            if followup is None
            else {
                "digest": followup.get("previous_review_digest"),
                "mode": followup.get("mode"),
                "reason": followup.get("reason"),
            }
        ),
        "completeness": {"retrieval_complete": bundle.get("retrieval_complete") is True},
        "inputs": {
            "bundle_path": bundle_path,
            "artifact_root": bundle.get("artifact_root"),
            "context_package_template": package.get("template_path"),
            "draft_path": followup.get("draft_path") if followup is not None else None,
        },
        "claim_notice": claim_notice(),
    }


# Read-only reconstruction of the prepared local view from recorded state:
# the pure follow-up plan (baseline, mode, delta, carried task) plus the
# saved draft's unfinished task and the exact recorded paths. No preparation
# is mutated and no evidence is collected again.
def _recorded_local_followup(
    root: str, bundle: dict[str, Any], bundle_path: str
) -> dict[str, Any] | None:
    from reviewmatic.local_review import (  # type: ignore[import-untyped,unused-ignore]
        local_followup_plan,
    )

    digest_value = contract.digest(
        contract.artifact_payload(Path(bundle_path), "local_wip_snapshot")[0]
    )
    draft_path = f"{root}/local-review-draft.json"
    template_path = f"{root}/local-context-package-input.json"
    paths: dict[str, Any] = {
        "draft_path": draft_path if Path(draft_path).exists() else None,
        "context_package": {
            "template_path": template_path if Path(template_path).exists() else None
        },
    }
    try:
        plan = dict(local_followup_plan(root, bundle, digest_value, "auto"))
    except contract.WorkflowError:
        return {
            "report_template": {},
            "previous_review_digest": None,
            "mode": None,
            "reason": None,
            **paths,
        }
    plan.pop("package_template_payload", None)
    if paths["draft_path"] is not None:
        try:
            draft = contract.read_json(
                contract.regular_file(Path(draft_path), "local review draft"), "local review draft"
            )
            if draft.get("evidence_digest") == digest_value and isinstance(draft.get("task"), dict):
                cast("dict[str, Any]", plan["report_template"])["task"] = draft["task"]
        except contract.WorkflowError:
            # An unreadable draft contributes no task; the recorded plan still stands.
            pass
    if not Path(template_path).exists():
        cast("dict[str, Any]", plan["context_package"])["template_path"] = None
    return plan


# Reads the recorded evidence behind an artifact root without recollecting.
def scope_for_root(root: str) -> dict[str, Any]:
    local_pointer = Path(root) / "current-local.json"
    if local_pointer.exists():
        pointer = contract.read_json(
            contract.regular_file(local_pointer, "local evidence pointer"), "pointer"
        )
        bundle_path = str(pointer["evidence_path"])
        _, bundle = contract.artifact_payload(Path(bundle_path), "local_wip_snapshot")
        return local_scope(bundle, _recorded_local_followup(root, bundle, bundle_path), bundle_path)
    progress_path = Path(root) / "review-current.json"
    if not progress_path.exists():
        raise contract.WorkflowError(
            "no prepared review state was found; run start-review or prepare-local first"
        )
    progress = contract.read_json(
        contract.regular_file(progress_path, "review progress"), "progress"
    )
    evidence_path_value = str(progress["evidence_path"])
    _, evidence = contract.artifact_payload(Path(evidence_path_value), "evidence_snapshot")
    context_path = (
        progress["context_path"] if isinstance(progress.get("context_path"), str) else None
    )
    return mr_scope(
        evidence=evidence,
        context_path=context_path,
        context_digest=(
            progress["context_digest"] if isinstance(progress.get("context_digest"), str) else None
        ),
        evidence_path=evidence_path_value,
        artifact_root=root,
        draft_path=progress.get("draft_path")
        if isinstance(progress.get("draft_path"), str)
        else None,
        repo_root=progress.get("repo_root") if isinstance(progress.get("repo_root"), str) else None,
    )
