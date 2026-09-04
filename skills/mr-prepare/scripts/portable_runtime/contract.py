#!/usr/bin/env python3
"""Portable, read-only collection and local publication-plan helpers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote as urlquote
from urllib.parse import urlsplit

MAX_BYTES = 8 * 1024 * 1024
MAX_PAGES = 1_000
URL_RE = re.compile(
    r"^https://(?P<host>[^/?#]+)/(?P<project>.+?)/-/(?P<kind>issues|merge_requests)/(?P<iid>[1-9][0-9]*)/?$"
)
SECRET_RE = re.compile(r"(?i)(token|password|secret|private[_-]?token)\s*[=:]\s*[^\s,]+")


class WorkflowError(ValueError):
    """An expected input, collection, or safety error."""


def redact(value: str) -> str:
    return SECRET_RE.sub(r"\1=[REDACTED]", value)


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def error(code: str, message: str, exit_code: int = 2) -> int:
    print(redact(message), file=sys.stderr)
    emit({"status": "error", "error": {"code": code, "message": redact(message), "retryable": False}})
    return exit_code


def capabilities(profile: str) -> int:
    emit(
        {
            "schema_version": 1,
            "payload_version": "1.0.0",
            "mutation": "local-write",
            "dry_run": True,
            "state_protocol": "local-artifacts",
            "external_tools": {"glab": shutil.which("glab") is not None},
            "destructive_flags": [],
            "profile": profile,
        }
    )
    return 0


def parse_target(value: str, expected: set[str]) -> dict[str, object]:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise WorkflowError("target must be a concrete HTTPS GitLab object URL")
    match = URL_RE.fullmatch(value)
    if match is None or match.group("kind") not in expected:
        raise WorkflowError("target must be one concrete GitLab issue or merge request URL")
    project = match.group("project")
    if not project or any(part in {"", ".", ".."} for part in project.split("/")):
        raise WorkflowError("target project path is unsafe")
    return {
        "url": value,
        "hostname": match.group("host").lower(),
        "project_path": project,
        "kind": match.group("kind"),
        "iid": int(match.group("iid")),
    }


def parse_project(value: str) -> dict[str, object]:
    parsed = urlsplit(value)
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or len(parts) < 2
        or "-" in parts
        or any(part in {".", ".."} for part in parts)
    ):
        raise WorkflowError("project must be an exact HTTPS GitLab project URL")
    return {
        "url": value.rstrip("/"),
        "hostname": parsed.hostname.lower(),
        "project_path": "/".join(parts),
        "kind": "new_issue",
        "iid": 0,
    }


def private_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise WorkflowError("artifact directory must be a real directory")
    path.chmod(0o700)
    return path.resolve()


def state_directory(profile: str, target: dict[str, object]) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", profile):
        raise WorkflowError("workflow profile is unsafe")
    home = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    identity = f"{target.get('hostname', 'local')}:{target.get('project_path', 'local')}:{target.get('kind', 'local')}:{target.get('iid', 'local')}"
    return private_directory(home / "agent-skills" / profile / hashlib.sha256(identity.encode()).hexdigest()[:20])


def artifact_root(path: Path) -> Path:
    home = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state")
    base = private_directory(home / "agent-skills")
    candidate = private_directory(path)
    try:
        relative = candidate.relative_to(base)
    except ValueError as exc:
        raise WorkflowError("artifact root is outside private workflow state") from exc
    if len(relative.parts) != 2 or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", relative.parts[0]):
        raise WorkflowError("artifact root is unsafe")
    return candidate


def regular_file(path: Path, label: str) -> Path:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise WorkflowError(f"{label} is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise WorkflowError(f"{label} must be a regular non-symlink file")
    if metadata.st_size > MAX_BYTES:
        raise WorkflowError(f"{label} exceeds the size limit")
    return path.resolve()


def write_json(path: Path, value: object) -> None:
    target = path.resolve()
    if target.parent != path.parent.resolve():
        raise WorkflowError("artifact path escapes its directory")
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, target)


def read_json(path: Path, label: str) -> dict[str, Any]:
    source = regular_file(path, label)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"{label} must contain a JSON object") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"{label} must contain a JSON object")
    return value


def glab_json(hostname: str, endpoint: str) -> object:
    glab = shutil.which("glab")
    if glab is None:
        raise WorkflowError("glab is unavailable; install and authenticate it outside this skill")
    try:
        completed = subprocess.run(
            [glab, "api", "--hostname", hostname, "--method", "GET", endpoint],
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkflowError("GitLab GET could not be completed") from exc
    if completed.returncode:
        raise WorkflowError(f"GitLab GET failed: {completed.stderr.strip() or completed.returncode}")
    if len(completed.stdout.encode()) > MAX_BYTES:
        raise WorkflowError("GitLab response exceeds the size limit")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise WorkflowError("GitLab returned invalid JSON") from exc


def paginated(hostname: str, endpoint: str) -> dict[str, object]:
    items: list[object] = []
    seen: set[str] = set()
    page_digests: set[str] = set()
    errors: list[str] = []
    for page in range(1, MAX_PAGES + 1):
        separator = "&" if "?" in endpoint else "?"
        try:
            value = glab_json(hostname, f"{endpoint}{separator}per_page=100&page={page}")
        except WorkflowError as exc:
            errors.append(str(exc))
            break
        if not isinstance(value, list):
            errors.append("GitLab pagination response is not an array")
            break
        page_digest = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        if page_digest in page_digests:
            errors.append("GitLab pagination repeated a page")
            break
        page_digests.add(page_digest)
        for item in value:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if key not in seen:
                seen.add(key)
                items.append(item)
        if len(value) < 100:
            return {"items": items, "complete": not errors, "errors": errors, "pages": page}
    if not errors:
        errors.append("pagination protective limit reached")
    return {"items": items, "complete": False, "errors": errors, "pages": MAX_PAGES}


def collect(target: dict[str, object], profile: str, *, persist: bool = True) -> dict[str, object]:
    hostname = str(target["hostname"])
    project_path = str(target["project_path"])
    project = glab_json(hostname, f"projects/{urlquote(project_path, safe='')}")
    if not isinstance(project, dict) or not isinstance(project.get("id"), int):
        raise WorkflowError("GitLab project identity is incomplete")
    project_id = project["id"]
    kind = str(target["kind"])
    iid = int(target["iid"])
    labels = paginated(hostname, f"projects/{project_id}/labels")
    if kind == "new_issue":
        root = state_directory(profile, target)
        bundle: dict[str, object] = {
            "schema_version": 1,
            "profile": profile,
            "target": target,
            "project": {"id": project_id, "path": project_path, "hostname": hostname},
            "object": {},
            "labels": labels,
            "changed_files": {"items": [], "complete": True, "errors": [], "pages": 0},
            "pipelines": {"items": [], "complete": True, "errors": [], "pages": 0},
            "head_sha": None,
            "artifact_root": str(root),
            "prepared_at": datetime.now(UTC).isoformat(),
            "retrieval_complete": bool(labels["complete"]),
        }
        if persist:
            write_json(root / "bundle.json", bundle)
        return bundle
    object_value = glab_json(hostname, f"projects/{project_id}/{kind}/{iid}")
    if not isinstance(object_value, dict):
        raise WorkflowError("GitLab target response is incomplete")
    changed: dict[str, object] = {"items": [], "complete": True, "errors": [], "pages": 0}
    pipelines: dict[str, object] = {"items": [], "complete": True, "errors": [], "pages": 0}
    refs = object_value.get("diff_refs")
    head_sha = refs.get("head_sha") if isinstance(refs, dict) else None
    if kind == "merge_requests":
        changes_value = glab_json(hostname, f"projects/{project_id}/merge_requests/{iid}/changes")
        if isinstance(changes_value, dict) and isinstance(changes_value.get("changes"), list):
            changed = {"items": changes_value["changes"], "complete": True, "errors": [], "pages": 1}
        else:
            changed = {"items": [], "complete": False, "errors": ["GitLab changed-files response is incomplete"], "pages": 1}
        if isinstance(head_sha, str) and head_sha:
            pipelines = paginated(hostname, f"projects/{project_id}/pipelines?sha={urlquote(head_sha, safe='')}")
    root = state_directory(profile, target)
    bundle: dict[str, object] = {
        "schema_version": 1,
        "profile": profile,
        "target": target,
        "project": {"id": project_id, "path": project_path, "hostname": hostname},
        "object": object_value,
        "labels": labels,
        "changed_files": changed,
        "pipelines": pipelines,
        "head_sha": head_sha,
        "artifact_root": str(root),
        "prepared_at": datetime.now(UTC).isoformat(),
        "retrieval_complete": bool(labels["complete"]) and bool(changed["complete"]) and bool(pipelines["complete"]),
    }
    if persist:
        write_json(root / "bundle.json", bundle)
    return bundle


def bundle_path(bundle: dict[str, Any]) -> Path:
    root_value = bundle.get("artifact_root")
    if not isinstance(root_value, str):
        raise WorkflowError("bundle has no artifact root")
    target = bundle.get("target")
    profile = bundle.get("profile")
    if not isinstance(target, dict) or not isinstance(profile, str):
        raise WorkflowError("bundle identity is incomplete")
    root = artifact_root(Path(root_value))
    if root != state_directory(profile, target):
        raise WorkflowError("bundle artifact root does not match its identity")
    return root


def plan_text(bundle: dict[str, Any], content: dict[str, Any]) -> str:
    target = bundle["target"]
    object_value = bundle["object"]
    if not isinstance(target, dict) or not isinstance(object_value, dict):
        raise WorkflowError("bundle is incomplete")
    title = content.get("title")
    description = content.get("description")
    def value(item: object) -> str:
        return str(item.get("value", "")) if isinstance(item, dict) else str(item or "")
    return "\n".join(
        [
            "# Проверенный план публикации",
            "",
            f"- Target: {target['url']}",
            f"- Проверенный SHA: {bundle.get('head_sha') or 'не применимо'}",
            f"- Полнота collection: {'полная' if bundle.get('retrieval_complete') else 'частичная'}",
            "- Этот skill не выполняет команды ниже.",
            "",
            "## Предлагаемые тексты",
            "",
            f"### Заголовок\n\n{value(title) or 'Без изменений.'}",
            f"\n### Описание\n\n{value(description) or 'Без изменений.'}",
            "",
            "## Ручная публикация",
            "",
            "Перед ручной публикацией повторно запусти `finalize`: изменённые SHA, метки или объект блокируют этот план.",
        ]
    ) + "\n"


def scaffold(bundle_file: str, content_file: str, plan_name: str) -> dict[str, object]:
    bundle = read_json(Path(bundle_file), "bundle")
    root = bundle_path(bundle)
    if Path(bundle_file).resolve() != root / "bundle.json":
        raise WorkflowError("bundle must be the canonical artifact bundle")
    content = read_json(Path(content_file), "content")
    plan = root / plan_name
    plan.write_text(plan_text(bundle, content), encoding="utf-8")
    plan.chmod(0o600)
    write_json(root / "scaffold.json", {"bundle_sha256": hashlib.sha256((root / "bundle.json").read_bytes()).hexdigest(), "plan": str(plan)})
    return {"status": "ok", "artifact_root": str(root), "plan": str(plan), "external_mutations": False}


def finalize(root_value: str) -> dict[str, object]:
    root = artifact_root(Path(root_value))
    bundle = read_json(root / "bundle.json", "bundle")
    target = bundle.get("target")
    if not isinstance(target, dict):
        raise WorkflowError("bundle target is missing")
    if target.get("kind") == "new_issue":
        result = {"status": "not_applicable", "changed": [], "head_sha": None, "retrieval_complete": bundle.get("retrieval_complete")}
        write_json(root / "finalize.json", result)
        return result
    current = collect(target, str(bundle.get("profile", "gitlab-workflow")), persist=False)
    baseline_object = bundle.get("object")
    current_object = current.get("object")
    if not isinstance(baseline_object, dict) or not isinstance(current_object, dict):
        raise WorkflowError("bundle object is missing")
    fields = ("updated_at", "labels", "diff_refs")
    changed = [field for field in fields if baseline_object.get(field) != current_object.get(field)]
    result = {"status": "stale" if changed else "ok", "changed": changed, "head_sha": current.get("head_sha"), "retrieval_complete": current.get("retrieval_complete")}
    write_json(root / "finalize.json", result)
    return result


def local_bundle(repo_root: str, profile: str, ref: str | None) -> dict[str, object]:
    raw_root = Path(repo_root)
    if raw_root.is_symlink():
        raise WorkflowError("repo root must not be a symbolic link")
    root = raw_root.resolve()
    if not (root / ".git").exists():
        raise WorkflowError("repo root must be a real Git checkout")
    git = shutil.which("git")
    if git is None:
        raise WorkflowError("git is unavailable")
    def run(*args: str) -> str:
        completed = subprocess.run([git, "-C", str(root), *args], check=False, capture_output=True, text=True)
        if completed.returncode:
            raise WorkflowError(f"git read failed: {completed.stderr.strip()}")
        return completed.stdout
    head = run("rev-parse", "HEAD").strip()
    base = run("merge-base", ref or "HEAD", "HEAD").strip() if ref else head
    diff = run("diff", "--find-renames", base, head, "--") if ref else run("diff", "--find-renames", "HEAD", "--")
    artifact = state_directory(profile, {"hostname": "local", "project_path": str(root), "kind": "local", "iid": 1})
    bundle = {"schema_version": 1, "profile": profile, "repo_root": str(root), "base_sha": base, "head_sha": head, "diff_sha256": hashlib.sha256(diff.encode()).hexdigest(), "diff": diff, "artifact_root": str(artifact), "working_tree": ref is None, "retrieval_complete": True}
    write_json(artifact / "local-bundle.json", bundle)
    return bundle


def finalize_local(bundle_file: str) -> dict[str, object]:
    bundle = read_json(Path(bundle_file), "local bundle")
    root_value = bundle.get("repo_root")
    base = bundle.get("base_sha")
    head = bundle.get("head_sha")
    digest = bundle.get("diff_sha256")
    if not all(isinstance(value, str) and value for value in (root_value, base, head, digest)):
        raise WorkflowError("local bundle identity is incomplete")
    root = Path(root_value)
    if root.is_symlink() or not (root / ".git").exists():
        raise WorkflowError("local bundle repository is unsafe")
    git = shutil.which("git")
    if git is None:
        raise WorkflowError("git is unavailable")
    def run(*arguments: str) -> str:
        completed = subprocess.run([git, "-C", str(root), *arguments], check=False, capture_output=True, text=True)
        if completed.returncode:
            raise WorkflowError("local Git input can no longer be read")
        return completed.stdout
    current_head = run("rev-parse", "HEAD").strip()
    current_diff = run("diff", "--find-renames", "HEAD", "--") if bundle.get("working_tree") is True else run("diff", "--find-renames", base, current_head, "--")
    current_digest = hashlib.sha256(current_diff.encode()).hexdigest()
    result = {"status": "ok" if current_head == head and current_digest == digest else "stale", "head_sha": current_head, "diff_sha256": current_digest}
    return result


def run(profile: str, expected: set[str], argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Portable read-only GitLab workflow helper")
    parser.add_argument("--capabilities", action="store_true")
    subparsers = parser.add_subparsers(dest="command")
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--url", action="append")
    prepare.add_argument("--project-url")
    scaffold_parser = subparsers.add_parser("scaffold")
    scaffold_parser.add_argument("--bundle", required=True)
    scaffold_parser.add_argument("--content", required=True)
    batch = subparsers.add_parser("scaffold-batch")
    batch.add_argument("--bundle", required=True)
    batch.add_argument("--content", required=True)
    final = subparsers.add_parser("finalize")
    final.add_argument("--artifact-root", required=True)
    final.add_argument("--report")
    local = subparsers.add_parser("prepare-local")
    local.add_argument("--repo-root", required=True)
    local.add_argument("--ref")
    local_final = subparsers.add_parser("finalize-local")
    local_final.add_argument("--bundle", required=True)
    mode = subparsers.add_parser("assess-mode")
    mode.add_argument("--mode", choices=("fast", "normal", "deep"), required=True)
    mode.add_argument("--critic-available", action="store_true")
    args = parser.parse_args(argv)
    if args.capabilities:
        return capabilities(profile)
    try:
        if args.command == "prepare":
            if bool(args.url) == bool(args.project_url):
                raise WorkflowError("provide exact --url target or --project-url, but not both")
            if args.project_url and profile != "task-prepare":
                raise WorkflowError("project creation mode is only available for task preparation")
            targets = [parse_target(value, expected) for value in args.url] if args.url else [parse_project(args.project_url)]
            results: list[dict[str, object]] = []
            for target in targets:
                try:
                    bundle = collect(target, profile)
                    results.append({"target": target["url"], "status": "ok", "artifact_root": bundle["artifact_root"], "head_sha": bundle["head_sha"], "complete": bundle["retrieval_complete"]})
                except WorkflowError as exc:
                    print(redact(str(exc)), file=sys.stderr)
                    results.append({"target": target["url"], "status": "error", "error": redact(str(exc))})
            status = "ok" if all(item["status"] == "ok" for item in results) else "partial"
            emit({"status": status, "items": results, "external_mutations": False})
            return 0 if status == "ok" else 1
        if args.command in {"scaffold", "scaffold-batch"}:
            emit(scaffold(args.bundle, args.content, "publication-plan.md" if args.command == "scaffold" else "batch-publication-plan.md"))
            return 0
        if args.command == "finalize":
            result = finalize(args.artifact_root)
            if profile == "release-review":
                if not args.report:
                    raise WorkflowError("release review finalize requires --report")
                report = read_json(Path(args.report), "release review report")
                gates = report.get("gates")
                required = {"semver", "compatibility", "migration", "rollback", "ci"}
                if (
                    report.get("status") != "completed"
                    or report.get("verdict") not in {"ready", "not_ready", "blocked"}
                    or not isinstance(report.get("readiness"), bool)
                    or not isinstance(gates, dict)
                    or set(gates) != required
                ):
                    raise WorkflowError("release review report has incomplete gates")
                for gate in gates.values():
                    if not isinstance(gate, dict) or gate.get("status") not in {"passed", "failed", "blocked", "not_applicable"} or gate.get("verified") is not True or not gate.get("evidence") or not isinstance(gate.get("inputs"), dict):
                        raise WorkflowError("release review gate is incomplete")
                object_value = bundle.get("object")
                project = bundle.get("project")
                refs = object_value.get("diff_refs") if isinstance(object_value, dict) else None
                if not isinstance(project, dict) or not isinstance(refs, dict):
                    raise WorkflowError("release review bundle identity is incomplete")
                expected_inputs = {
                    "hostname": project.get("hostname"),
                    "project_id": project.get("id"),
                    "iid": bundle.get("target", {}).get("iid") if isinstance(bundle.get("target"), dict) else None,
                    "target_branch": object_value.get("target_branch"),
                    "base_sha": refs.get("base_sha"),
                    "start_sha": refs.get("start_sha"),
                    "head_sha": bundle.get("head_sha"),
                }
                for gate_name, gate in gates.items():
                    inputs = gate["inputs"]
                    if any(inputs.get(key) != value for key, value in expected_inputs.items()):
                        raise WorkflowError("release review gate does not bind the exact target identity")
                    if gate_name == "ci" and (inputs.get("pipeline_sha") != bundle.get("head_sha") or not isinstance(inputs.get("pipeline_status"), str) or not inputs["pipeline_status"]):
                        raise WorkflowError("release review CI gate does not bind the exact head pipeline")
                if (report["verdict"] == "ready") != report["readiness"]:
                    raise WorkflowError("release review verdict and readiness disagree")
                result["report_valid"] = True
            emit(result)
            return 0 if result["status"] in {"ok", "not_applicable"} else 2
        if args.command == "prepare-local":
            bundle = local_bundle(args.repo_root, profile, args.ref)
            emit({"status": "ok", "bundle": str(Path(str(bundle["artifact_root"])) / "local-bundle.json"), "head_sha": bundle["head_sha"], "external_mutations": False})
            return 0
        if args.command == "finalize-local":
            result = finalize_local(args.bundle)
            emit(result)
            return 0 if result["status"] == "ok" else 2
        if args.command == "assess-mode":
            if args.mode in {"normal", "deep"} and not args.critic_available:
                emit({"status": "unsupported", "reason": "independent critic host capability is required", "details": {"mode": args.mode}})
                return 4
            emit({"status": "ok", "mode": args.mode, "independent_critic_required": args.mode in {"normal", "deep"}})
            return 0
        return error("invalid_command", "a supported subcommand is required")
    except WorkflowError as exc:
        code = "tool_unavailable" if "unavailable" in str(exc) else "invalid_input"
        return error(code, str(exc), 3 if code == "tool_unavailable" else 2)
