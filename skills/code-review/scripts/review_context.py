#!/usr/bin/env python3
"""Collect role, thread, and exact local Git context for one MR review."""

from __future__ import annotations

import hashlib
import shlex
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from shared.references.portable_gitlab import contract as portable
else:
    from portable_runtime import contract as portable


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
    evidence: dict[str, Any], evidence_digest: str, repo_root: str
) -> dict[str, Any]:
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
    if not current_username:
        raise portable.WorkflowError("current GitLab username is unavailable")
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
    return {
        "schema_version": portable.ARTIFACT_VERSION,
        "profile": "code-review",
        "external_mutations": False,
        "evidence_digest": evidence_digest,
        "target": target,
        "role": role,
        "current_user_username": current_username,
        "mr_author_username": author_username,
        "discussions": discussions,
        "notes": notes,
        "counts": counts,
        "exact_git": exact_git,
        "complete": evidence.get("retrieval_complete") is True
        and notes_component["complete"] is True
        and not errors,
        "errors": errors,
        "artifact_root": evidence["artifact_root"],
        "prepared_at": datetime.now(UTC).isoformat(),
    }


def prepare_context(evidence_value: str, repo_root: str) -> dict[str, object]:
    _, evidence, root, evidence_digest = evidence_context(evidence_value)
    context = collect_context(evidence, evidence_digest, repo_root)
    path, context_digest = portable.write_artifact(root, "review_context", context)
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


def refresh_context(context: dict[str, Any], evidence_value: str | Path) -> dict[str, Any]:
    _, evidence, _, evidence_digest = evidence_context(evidence_value)
    exact_git = context.get("exact_git")
    repo_root = exact_git.get("repo_root") if isinstance(exact_git, dict) else None
    if not isinstance(repo_root, str):
        raise portable.WorkflowError("review context repository root is unavailable")
    return collect_context(evidence, evidence_digest, repo_root)


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


def finding_body(finding: dict[str, Any]) -> str:
    return (
        "\n".join(
            [
                f"### {finding['severity'].title()}: {finding['summary']}",
                "",
                f"- Finding ID: `{finding['id']}`",
                f"- Risk: {finding['risk']}",
                "- Evidence:",
                *[f"  - {value}" for value in finding["evidence"]],
                f"- Consequence: {finding['consequence']}",
                f"- Relation to change: {finding['relation_to_change']}",
                f"- Minimum fix: {finding['minimum_fix']}",
            ]
        )
        + "\n"
    )


def publication_preview(
    evidence: dict[str, Any], root: Path, findings: list[dict[str, Any]]
) -> dict[str, Any]:
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
        raise portable.WorkflowError("MR identity is incomplete for publication preview")
    hostname = cast(str, project["hostname"])
    state = cast(str, object_value["state"])
    endpoint = f"projects/{project['id']}/merge_requests/{target['iid']}"
    endpoint_argument = shlex.quote(endpoint)
    preflight = (
        f"glab api --hostname {shlex.quote(hostname)} --method GET {endpoint_argument} "
        f"| jq -e --arg expected_state {shlex.quote(state)} --arg expected_head {shlex.quote(cast(str, head_sha))} "
        + shlex.quote(".state == $expected_state and .diff_refs.head_sha == $expected_head")
    )
    body_directory = portable.private_directory(root / "artifacts" / "review_plan" / "bodies")
    body_files: list[dict[str, str]] = []
    commands: list[dict[str, str]] = []
    for finding in findings:
        body = finding_body(finding)
        body_digest = hashlib.sha256(body.encode()).hexdigest()
        identity_digest = hashlib.sha256(finding["id"].encode()).hexdigest()[:12]
        body_path, actual_digest = portable.write_companion(
            body_directory / f"{identity_digest}-{body_digest}.md", body
        )
        body_files.append(
            {
                "finding_id": finding["id"],
                "path": str(body_path),
                "sha256": actual_digest,
                "content": body,
            }
        )
        commands.append(
            {
                "finding_id": finding["id"],
                "command": (
                    f"{preflight} && "
                    f"printf '%s  %s\\n' {shlex.quote(actual_digest)} {shlex.quote(str(body_path))} "
                    "| sha256sum --check --status && "
                    f"glab api --hostname {shlex.quote(hostname)} --method POST "
                    f"{shlex.quote(f'{endpoint}/notes')} "
                    f"-F {shlex.quote(f'body=@{body_path}')}"
                ),
            }
        )
    result = {
        "mr_state": state,
        "warning": (
            f"Commands are prepared for manual execution for an MR in state {state}; "
            "they were not executed by code-review."
        ),
        "preflight_command": preflight,
        "body_files": body_files,
        "commands": commands,
    }
    if not portable.review_publication_preview_is_valid(result):
        raise portable.WorkflowError("review publication preview is invalid")
    return result


def review_markdown(
    evidence: dict[str, Any],
    context: dict[str, Any],
    decision: dict[str, Any],
    content: dict[str, Any],
    metadata: dict[str, Any],
    publication: dict[str, Any],
) -> str:
    observed = cast(dict[str, Any], metadata["observed"])
    assessment = cast(dict[str, dict[str, Any]], metadata["assessment"])
    lines = [
        "# Verified code review",
        "",
        f"- Target: {context['target'].get('url')}",
        f"- Role: `{context['role']}`",
        f"- Mode: `{decision['mode']}`",
        f"- Verdict: `{decision['verdict']}`",
        f"- Base SHA: {evidence.get('base_sha')}",
        f"- Start SHA: {evidence.get('start_sha')}",
        f"- Head SHA: {evidence.get('head_sha')}",
        "- `external_mutations=false`: this review does not publish, resolve, approve, merge, push, or edit project files.",
        "",
        "## Summary",
        "",
        content["summary"],
        "",
        "## MR metadata assessment",
        "",
        f"- Current title: {observed['title']}",
        f"- Current labels: {markdown_cell(observed['labels'])}",
        f"- Current workflow state: `{observed['workflow_state']}`",
        "",
        "### Current description",
        "",
        portable.marked_preview("CURRENT MR DESCRIPTION", observed["description"] or ""),
        "",
        "| Field | Status | Rationale | Recommendation |",
        "|---|---|---|---|",
        *[
            "| "
            + " | ".join(
                [
                    field,
                    markdown_cell(assessment[field]["status"]),
                    markdown_cell(assessment[field]["rationale"]),
                    markdown_cell(assessment[field]["recommendation"] or "none"),
                ]
            )
            + " |"
            for field in ("title", "description", "labels", "workflow_state", "overall")
        ],
        "",
        "## Findings",
        "",
    ]
    findings = cast(list[dict[str, Any]], content["findings"])
    if not findings:
        lines.append("No findings discovered.")
    for finding in findings:
        lines.extend(
            [
                f"### {finding['severity'].title()}: {finding['summary']}",
                "",
                f"- ID: `{finding['id']}`",
                f"- Risk: {finding['risk']}",
                "- Evidence:",
                *[f"  - {value}" for value in finding["evidence"]],
                f"- Consequence: {finding['consequence']}",
                f"- Relation to change: {finding['relation_to_change']}",
                f"- Minimum fix: {finding['minimum_fix']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Thread decisions",
            "",
            "| Thread | State | Assessment | Outcome | Rationale |",
            "|---|---|---|---|---|",
        ]
    )
    decisions = cast(list[dict[str, Any]], content["thread_decisions"])
    if not decisions:
        lines.append("| None | - | - | - | No non-system threads. |")
    for item in decisions:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"[{markdown_cell(item['id'])}]({item['url']})",
                    markdown_cell(item["state"]),
                    markdown_cell(item["assessment"]),
                    markdown_cell(item["outcome"]),
                    markdown_cell(item["rationale"]),
                ]
            )
            + " |"
        )
        if item["proposed_response"]:
            lines.extend(
                [
                    "",
                    f"Proposed response for [{item['id']}]({item['url']}):",
                    "",
                    portable.marked_preview(
                        f"THREAD {item['id']} PROPOSED RESPONSE", item["proposed_response"]
                    ),
                ]
            )
    lines.extend(
        [
            "",
            "## Architecture assessment",
            "",
            content["architecture_assessment"],
            "",
            "## SemVer impact",
            "",
            f"`{content['semver_impact']}`",
            "",
            content["semver_rationale"],
            "",
            "## Checks",
            "",
            *[f"- {value}" for value in content["checks"]],
            "",
            "## Manual publication preview",
            "",
            f"- MR state: `{publication['mr_state']}`",
            f"- Warning: {publication['warning']}",
            "",
            "### Preflight",
            "",
            "```shell",
            publication["preflight_command"],
            "```",
        ]
    )
    body_by_id = {
        item["finding_id"]: item for item in cast(list[dict[str, str]], publication["body_files"])
    }
    commands = cast(list[dict[str, str]], publication["commands"])
    if not commands:
        lines.extend(["", "No findings require publication commands."])
    for item in commands:
        body = body_by_id[item["finding_id"]]
        lines.extend(
            [
                "",
                f"### Finding {item['finding_id']}",
                "",
                f"- Body path: `{body['path']}`",
                f"- Body SHA-256: `{body['sha256']}`",
                "",
                portable.marked_preview(f"FINDING {item['finding_id']} BODY", body["content"]),
                "",
                "```shell",
                f"# Publish finding {item['finding_id']} after the preflight succeeds.",
                item["command"],
                "```",
            ]
        )
    return "\n".join(lines) + "\n"


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
        or context_fingerprint(context) != context_fingerprint(current_context)
    ):
        raise portable.WorkflowError("review evidence or context is stale before plan creation")
    content = portable.exact_keys(
        portable.read_json(Path(content_value), "review plan content"),
        {
            "summary",
            "architecture_assessment",
            "semver_impact",
            "semver_rationale",
            "mr_metadata_assessment",
            "checks",
            "findings",
            "thread_decisions",
        },
        "review plan content",
    )
    if (
        not portable.nonempty_string(content["summary"])
        or not portable.nonempty_string(content["architecture_assessment"])
        or content["semver_impact"] not in {"major", "minor", "patch", "none", "not_applicable"}
        or not portable.nonempty_string(content["semver_rationale"])
        or not isinstance(content["checks"], list)
        or not all(portable.nonempty_string(value) for value in content["checks"])
        or not portable.detailed_findings_are_valid(content["findings"])
        or not portable.thread_decisions_are_valid(content["thread_decisions"])
    ):
        raise portable.WorkflowError("review plan content is invalid")
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    findings = cast(list[dict[str, Any]], content["findings"])
    finding_ids = [finding["id"] for finding in findings]
    if len(finding_ids) != len(set(finding_ids)):
        raise portable.WorkflowError("review finding IDs must be unique")
    if findings != sorted(findings, key=lambda item: severity_order[item["severity"]]):
        raise portable.WorkflowError("review findings must be ordered by severity")
    if decision.get("findings") != findings:
        raise portable.WorkflowError("review plan findings do not match the review decision")
    discussions = cast(list[dict[str, Any]], context["discussions"])
    expected_threads = {
        str(item["root_note_id"]): item for item in discussions if item.get("root_system") is False
    }
    discussion_note_ids = {
        str(note.get("id"))
        for discussion in discussions
        for note in cast(list[dict[str, Any]], discussion.get("notes", []))
    }
    for note in cast(list[dict[str, Any]], context["notes"]):
        note_id = str(note.get("id"))
        if note.get("system") is not True and note_id not in discussion_note_ids:
            expected_threads[note_id] = {"root_note_url": note.get("note_url")}
    thread_decisions = cast(list[dict[str, Any]], content["thread_decisions"])
    actual_threads = {item["id"]: item for item in thread_decisions}
    if len(actual_threads) != len(thread_decisions) or set(actual_threads) != set(expected_threads):
        raise portable.WorkflowError("review plan must account for every non-system thread")
    for thread_id, item in actual_threads.items():
        if item["url"] != expected_threads[thread_id].get("root_note_url"):
            raise portable.WorkflowError("thread decision URL does not match review context")
    if context["role"] == "reviewer" and any(
        item["outcome"] == "local_fix" for item in thread_decisions
    ):
        raise portable.WorkflowError("reviewer thread decisions cannot promise local fixes")
    metadata = metadata_assessment(evidence, content["mr_metadata_assessment"])
    publication = publication_preview(evidence, root, findings)
    markdown = review_markdown(evidence, context, decision, content, metadata, publication)
    payload = {
        "profile": "code-review",
        "external_mutations": False,
        "evidence_digest": evidence_digest,
        "context_digest": context_digest,
        "decision_digest": decision_digest,
        "target": context["target"],
        "role": context["role"],
        "mode": decision["mode"],
        "verdict": decision["verdict"],
        "complete": evidence.get("retrieval_complete") is True and context.get("complete") is True,
        "summary": content["summary"],
        "architecture_assessment": content["architecture_assessment"],
        "semver_impact": content["semver_impact"],
        "semver_rationale": content["semver_rationale"],
        "mr_metadata_assessment": metadata,
        "publication_preview": publication,
        "checks": content["checks"],
        "findings": findings,
        "thread_decisions": thread_decisions,
        "markdown": markdown,
    }
    path, plan_digest = portable.write_artifact(root, "review_plan", payload)
    markdown_path, markdown_digest = portable.write_companion(path.with_suffix(".md"), markdown)
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
        "publication_commands": [item["command"] for item in publication["commands"]],
        "external_mutations": False,
    }
