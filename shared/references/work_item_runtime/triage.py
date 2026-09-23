#!/usr/bin/env python3
"""Collect and persist bounded GitLab task-triage evidence and reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn

ISSUE_RE = re.compile(
    r"https://(?P<host>[A-Za-z0-9.-]+)/(?P<project>.+?)/-/(?:issues|work_items)/(?P<iid>[1-9][0-9]*)/?$"
)
COLLECTION_RE = re.compile(
    r"https://(?P<host>[A-Za-z0-9.-]+)/(?P<project>.+?)/-/(?:issues|work_items)/?$"
)
DIGEST_RE = re.compile(r"[a-f0-9]{64}")
MAX_PAGES = 100
MAX_ITEMS = 500
SEMVER = {"major", "minor", "patch", "none", "unknown"}
ACTUALITY = {"current", "implemented", "obsolete", "duplicate", "unknown"}
VERDICTS = {"ready", "needs_clarification", "blocked"}


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
    allowed = {"state", "label_name[]", "labels", "search", "assignee_username"}
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
    if len(searches) > 1 or len(assignees) > 1:
        raise WorkflowError("collection sources contain conflicting filters")
    if args.search and searches and args.search not in searches:
        raise WorkflowError("collection sources contain conflicting search filters")
    if args.assignee and assignees and args.assignee not in assignees:
        raise WorkflowError("collection sources contain conflicting assignee filters")
    result = {"state": state}
    if labels:
        result["labels"] = ",".join(sorted(labels))
    search = args.search or next(iter(searches), None)
    assignee = args.assignee or next(iter(assignees), None)
    if search:
        result["search"] = search
    if assignee:
        result["assignee_username"] = assignee
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
    source = {
        "target": target,
        "issue": issue,
        "discussions": discussions,
        "links": links,
        "merge_requests": merge_requests,
        "closed_by": closed_by,
    }
    return {**source, "source_fingerprint": digest(source)}


def project_context(targets: list[dict[str, Any]]) -> dict[str, Any]:
    contexts: dict[str, Any] = {}
    projects = {(item["hostname"], item["project_id"]): item for item in targets}
    for (hostname, project_id), target in sorted(projects.items()):
        issues = paginated(hostname, f"projects/{project_id}/issues?state=all")
        labels = paginated(hostname, f"projects/{project_id}/labels?include_ancestor_groups=true")
        key = f"{hostname}:{project_id}"
        contexts[key] = {
            "project_path": target["project_path"],
            "issues": issues,
            "labels": labels,
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
    scope = {
        "sources": sorted(source["canonical_url"] for source in sources),
        "filters": filters,
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
                and isinstance(cached.get("analysis"), dict)
            )
            items.append(
                {
                    "target": target,
                    "url": str(evidence["issue"].get("web_url") or ""),
                    "evidence_path": str(artifact),
                    "evidence_digest": evidence_digest,
                    "source_fingerprint": evidence["source_fingerprint"],
                    "analysis_required": not reusable,
                    "cached_analysis": cached.get("analysis") if reusable else None,
                }
            )
        except WorkflowError as exc:
            errors.append({"target": item_key(target), "message": str(exc)})
    payload = {
        "schema": "task-triage/collection-evidence/v1",
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
        "schema": "task-triage/current/v1",
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
    if collection.get("schema") != "task-triage/collection-evidence/v1":
        raise WorkflowError("collection artifact schema is invalid")
    return collection, digest_value, path.parent.resolve()


def text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkflowError(f"{label} must be non-empty text")
    return value.strip()


def validate_analysis(collection: dict[str, Any], analysis: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = analysis.get("items")
    if not isinstance(raw_items, list):
        raise WorkflowError("analysis items must be a list")
    evidence = {item["evidence_digest"]: item for item in collection["items"]}
    if len(raw_items) != len(evidence):
        raise WorkflowError("analysis must contain every collected issue exactly once")
    seen: set[str] = set()
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
        semver = raw.get("semver")
        if not isinstance(actuality, dict) or actuality.get("status") not in ACTUALITY:
            raise WorkflowError("analysis actuality is invalid")
        if not isinstance(quality, dict) or quality.get("verdict") not in VERDICTS:
            raise WorkflowError("analysis quality verdict is invalid")
        if not isinstance(semver, dict) or semver.get("level") not in SEMVER:
            raise WorkflowError("analysis SemVer assessment is invalid")
        for field in ("severity", "priority"):
            text(raw.get(field), f"items[{position}].{field}")
        result.append({**raw, "evidence": evidence[evidence_digest]})
    return result


def markdown_list(value: object) -> str:
    if not isinstance(value, list) or not value:
        return "- None observed."
    return "\n".join(f"- {item}" for item in value)


def command_for(root: Path, item: dict[str, Any]) -> list[str]:
    proposed = item.get("proposed_changes")
    if not isinstance(proposed, dict):
        return []
    target = item["evidence"]["target"]
    host, project_id, iid = target["hostname"], target["project_id"], target["iid"]
    commands: list[str] = []
    update = {key: proposed[key] for key in ("title", "description", "labels") if key in proposed}
    if update:
        if isinstance(update.get("labels"), list):
            update["labels"] = ",".join(str(label) for label in update["labels"])
        request, _ = write_artifact(root, "commands", update)
        commands.append(
            f'glab api --hostname "{host}" --method PUT "projects/{project_id}/issues/{iid}" --input "{request}"'
        )
    links = proposed.get("links", [])
    if not isinstance(links, list):
        raise WorkflowError("proposed links must be a list")
    for link in links:
        if (
            not isinstance(link, dict)
            or not isinstance(link.get("target_project_id"), int)
            or not isinstance(link.get("target_issue_iid"), int)
        ):
            raise WorkflowError("proposed issue link is invalid")
        request, _ = write_artifact(root, "commands", link)
        commands.append(
            f'glab api --hostname "{host}" --method POST "projects/{project_id}/issues/{iid}/links" --input "{request}"'
        )
    return commands


def item_markdown(item: dict[str, Any], commands: list[str]) -> str:
    evidence = item["evidence"]
    issue = read_object(Path(evidence["evidence_path"]), "issue evidence")["issue"]
    actuality, quality, semver = item["actuality"], item["quality"], item["semver"]
    sections = [
        f"# {issue.get('title', evidence['url'])}",
        "",
        f"- Source: {evidence['url']}",
        f"- Actuality: {actuality['status']}",
        f"- Quality: {quality['verdict']}",
        f"- SemVer: {semver['level']}",
        f"- Severity: {item['severity']}",
        f"- Priority: {item['priority']}",
        "",
        "## Actuality",
        "",
        text(actuality.get("rationale"), "actuality rationale"),
        "",
        "## Quality findings",
        "",
        markdown_list(quality.get("findings")),
        "",
        "## Duplicates and relations",
        "",
        markdown_list(item.get("duplicates")),
        "",
        markdown_list(item.get("related_issues")),
        "",
        "## Merge requests",
        "",
        markdown_list(item.get("merge_requests")),
        "",
        "## SemVer",
        "",
        text(semver.get("rationale"), "SemVer rationale"),
        "",
        "## Recommendations",
        "",
        markdown_list(item.get("recommendations")),
        "",
        "## Manual commands",
        "",
    ]
    if commands:
        sections.extend(["```sh", *commands, "```"])
    else:
        sections.append("No GitLab changes are recommended.")
    return "\n".join(sections) + "\n"


def publish(args: argparse.Namespace) -> dict[str, Any]:
    collection, collection_digest, root = resolve_collection(Path(args.collection).resolve())
    analysis = read_object(Path(args.analysis).resolve(), "triage analysis")
    if analysis.get("collection_digest") != collection_digest:
        raise WorkflowError("analysis is stale for the selected collection")
    items = validate_analysis(collection, analysis)
    reports = private_directory(root / "reports")
    report_entries: list[dict[str, str]] = []
    analysis_index = load_analysis_index(root)["items"]
    for item in items:
        commands = command_for(root, item)
        target = item["evidence"]["target"]
        report = reports / f"{target['hostname']}-{target['project_id']}-{target['iid']}.md"
        atomic_write(report, item_markdown(item, commands).encode())
        report_entries.append({"url": item["evidence"]["url"], "report": str(report)})
        analysis_index[item_key(target)] = {
            "source_fingerprint": item["evidence"]["source_fingerprint"],
            "analysis": {key: value for key, value in item.items() if key != "evidence"},
        }
    artifact_value = {
        "schema": "task-triage/analysis/v1",
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
    artifact, analysis_digest = write_artifact(root, "analysis", artifact_value)
    write_json(root / "analysis-index.json", {"items": analysis_index})
    summary_lines = [
        "# Task triage summary",
        "",
        f"- Status: {'complete' if collection['complete'] and not artifact_value['questions'] else 'partial'}",
        f"- Collection evidence: `{collection_digest}`",
        f"- Analysis: `{analysis_digest}`",
        "",
        "## First tasks",
        "",
        markdown_list(artifact_value["top_five"][:5]),
        "",
        "## Parallel groups",
        "",
        markdown_list(artifact_value["parallel_groups"]),
        "",
        "## Questions",
        "",
        markdown_list(artifact_value["questions"]),
        "",
        "## Detailed reports",
        "",
        *[f"- [{entry['url']}]({entry['report']})" for entry in report_entries],
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
        "status": "ok" if collection["complete"] and not artifact_value["questions"] else "partial",
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
                        "payload_version": "1.0.0",
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
