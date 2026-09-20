"""Render bounded, manual-only GitLab task plans from agent-assessed evidence."""

from __future__ import annotations

import json
import os
import re
import shlex
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .contract import Parser, WorkflowError, atomic_write, digest, emit, output_path

CHECKS = {"target", "templates", "metadata", "duplicates", "semantics"}
TEXT = {
    "en": {
        "title": "Task publication plan",
        "manual": "Run commands manually after reviewing the text. Creation commands are not idempotent. Check GitLab before retrying. Keep this directory until publication is complete.",
        "ready": "Ready to create",
        "blocked": "Publication blocked",
        "existing": "Already exists: creation omitted",
        "checks": "Checks and open questions",
        "links": "Dependencies",
        "deferred": "Deferred: obtain and verify both real issue IIDs, then regenerate this plan. Do not repeat creation commands.",
        "unsupported": "Deferred: this relationship needs a verified API supported by the target instance.",
        "target": "Target",
        "unresolved": "Destination is unresolved; select and verify the GitLab namespace.",
        "metadata": "Publication metadata",
        "check_target": "Destination and API",
        "check_templates": "Template",
        "check_metadata": "Metadata",
        "check_duplicates": "Existing work",
        "check_semantics": "Task meaning and verification",
    },
    "ru": {
        "title": "План создания задач",
        "manual": "Выполни команды вручную после проверки текста. Команды создания не идемпотентны: перед повтором проверь GitLab. Сохрани эту директорию до завершения публикации.",
        "ready": "Готово к созданию",
        "blocked": "Публикация заблокирована",
        "existing": "Уже существует: команда создания не нужна",
        "checks": "Проверки и открытые вопросы",
        "links": "Зависимости",
        "deferred": "Отложено: получи и проверь реальные IID обеих задач, затем обнови план. Не повторяй команды создания.",
        "unsupported": "Отложено: для этой связи нужно проверить API, поддерживаемое целевой инсталляцией.",
        "target": "Место публикации",
        "unresolved": "Место публикации не определено: выбери и проверь проект или группу GitLab.",
        "metadata": "Метаданные публикации",
        "check_target": "Место публикации и API",
        "check_templates": "Шаблон",
        "check_metadata": "Метаданные",
        "check_duplicates": "Существующие задачи",
        "check_semantics": "Смысл задачи и проверка результата",
    },
}


def fields(value: object, keys: set[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise WorkflowError(f"{name}: expected fields {', '.join(sorted(keys))}")
    return value


def text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and "\x00" not in value


def positive(value: object) -> bool:
    return type(value) is int and value > 0


def validate_target(value: object) -> None:
    if value is None:
        return
    target = fields(value, {"kind", "id", "url"}, "target")
    if target["kind"] not in ("project", "group") or not positive(target["id"]):
        raise WorkflowError("target requires an observed project/group ID")
    if not text(target["url"]):
        raise WorkflowError("target requires an exact HTTPS namespace URL")
    url = urlsplit(target["url"])
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
        or not re.fullmatch(r"[A-Za-z0-9.:-]+", url.netloc)
        or not re.fullmatch(r"/[A-Za-z0-9_.\-/]+", url.path)
        or any(part in {".", "..", "-"} for part in url.path.split("/"))
        or (target["kind"] == "group") != url.path.startswith("/groups/")
    ):
        raise WorkflowError("target must be an exact HTTPS project or /groups/ namespace URL")


def validate(value: object) -> dict[str, Any]:
    plan = fields(value, {"version", "locale", "batch_agreement", "items", "links"}, "plan")
    if plan["version"] != 1 or plan["locale"] not in TEXT:
        raise WorkflowError("unsupported publication version or locale")
    items = plan["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= 50:
        raise WorkflowError("plan requires 1 to 50 items")
    if not isinstance(plan["batch_agreement"], str) or (
        len(items) > 1 and not text(plan["batch_agreement"])
    ):
        raise WorkflowError("multiple items require the user's batch agreement")
    ids: set[str] = set()
    for raw in items:
        item = fields(
            raw,
            {"key", "title", "description", "target", "type", "metadata", "checks", "existing_iid"},
            "item",
        )
        key = item["key"]
        if isinstance(key, str) and (key == "task-publication" or re.fullmatch(r"link-\d+", key)):
            raise WorkflowError("item key conflicts with a reserved artifact name")
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", key) or key in ids:
            raise WorkflowError("item keys must be unique safe identifiers")
        ids.add(key)
        if not text(item["title"]) or any(c in item["title"] for c in "\r\n"):
            raise WorkflowError("item title must be one nonempty line")
        if not text(item["description"]) or item["type"] not in ("issue", "epic"):
            raise WorkflowError("item requires a description and issue/epic type")
        validate_target(item["target"])
        target = item["target"]
        if target is not None and (item["type"] == "issue") != (target["kind"] == "project"):
            raise WorkflowError("issues require projects; epics require groups")
        if item["existing_iid"] is not None and not positive(item["existing_iid"]):
            raise WorkflowError("existing_iid must be an observed positive IID or null")
        checks = fields(item["checks"], CHECKS, "checks")
        for raw_check in checks.values():
            checked = fields(raw_check, {"status", "detail"}, "check")
            if checked["status"] not in ("verified", "blocked") or not text(checked["detail"]):
                raise WorkflowError("checks require verified/blocked status and evidence detail")
        metadata = item["metadata"]
        if not isinstance(metadata, dict) or set(metadata) - {
            "labels",
            "assignee_ids",
            "milestone_id",
            "confidential",
        }:
            raise WorkflowError("unsupported metadata")
        if item["type"] == "epic" and set(metadata) - {"labels", "confidential"}:
            raise WorkflowError("epic metadata supports only labels and confidential")
        if "labels" in metadata and (
            not isinstance(metadata["labels"], list)
            or not all(text(label) and "," not in label for label in metadata["labels"])
        ):
            raise WorkflowError("labels must be observed names without commas")
        if "assignee_ids" in metadata and (
            not isinstance(metadata["assignee_ids"], list)
            or not all(positive(identifier) for identifier in metadata["assignee_ids"])
        ):
            raise WorkflowError("assignees must be observed numeric IDs")
        if "milestone_id" in metadata and not positive(metadata["milestone_id"]):
            raise WorkflowError("milestone_id must be an observed numeric ID")
        if "confidential" in metadata and type(metadata["confidential"]) is not bool:
            raise WorkflowError("confidential must be boolean")
    if not isinstance(plan["links"], list):
        raise WorkflowError("links must be a list")
    edges: dict[str, list[str]] = {key: [] for key in ids}
    seen: set[tuple[str, str]] = set()
    for raw in plan["links"]:
        link = fields(raw, {"source", "target", "rationale", "verified"}, "link")
        source, target = link["source"], link["target"]
        if not isinstance(source, str) or not isinstance(target, str):
            raise WorkflowError("link references must be item keys")
        if source not in ids or target not in ids or source == target or (source, target) in seen:
            raise WorkflowError("link references must exist and be distinct and unique")
        if not text(link["rationale"]) or type(link["verified"]) is not bool:
            raise WorkflowError("link requires a rationale and verification status")
        seen.add((source, target))
        edges[source].append(target)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(key: str) -> None:
        if key in visiting:
            raise WorkflowError("dependency cycle")
        if key in visited:
            return
        visiting.add(key)
        for target in edges[key]:
            visit(target)
        visiting.remove(key)
        visited.add(key)

    for key in ids:
        visit(key)
    return plan


def ready(item: dict[str, Any]) -> bool:
    return item["target"] is not None and all(
        check["status"] == "verified" for check in item["checks"].values()
    )


def api_command(host: str, endpoint: str, payload: Path) -> str:
    return shlex.join(
        [
            "glab",
            "api",
            "--hostname",
            host,
            "--method",
            "POST",
            endpoint,
            "--header",
            "Content-Type: application/json",
            "--input",
            str(payload),
        ]
    )


def code_block(command: str) -> str:
    fence = "`" * max(3, max((len(s) + 1 for s in re.findall(r"`+", command)), default=3))
    return f"{fence}sh\n{command}\n{fence}"


def render(plan: dict[str, Any], root: Path) -> tuple[dict[str, bytes], bool]:
    labels = TEXT[plan["locale"]]
    lines = [f"# {labels['title']}", "", labels["manual"], ""]
    files: dict[str, bytes] = {}
    complete = True
    items = {item["key"]: item for item in plan["items"]}
    for item in items.values():
        key = item["key"]
        is_ready = ready(item)
        complete = complete and is_ready
        state = "blocked" if not is_ready else "existing" if item["existing_iid"] else "ready"
        lines.extend([f"## {item['title']}", "", labels[state], ""])
        if item["target"]:
            target = item["target"]
            lines.extend([f"{labels['target']}: {target['url']} ({item['type']})", ""])
            if item["existing_iid"]:
                lines.extend(
                    [f"{target['url'].rstrip('/')}/-/{item['type']}s/{item['existing_iid']}", ""]
                )
        else:
            lines.extend([labels["unresolved"], ""])
        if item["metadata"]:
            lines.extend(
                [
                    f"### {labels['metadata']}",
                    "",
                    "```json",
                    json.dumps(item["metadata"], ensure_ascii=False, indent=2),
                    "```",
                    "",
                ]
            )
        lines.extend([item["description"], "", f"### {labels['checks']}", ""])
        for name in sorted(CHECKS):
            check = item["checks"][name]
            marker = "x" if check["status"] == "verified" else " "
            lines.append(f"- [{marker}] {labels['check_' + name]}: {check['detail']}")
        lines.append("")
        files[f"{key}.md"] = item["description"].encode()
        if is_ready and item["existing_iid"] is None:
            metadata = dict(item["metadata"])
            if "labels" in metadata:
                metadata["labels"] = ",".join(metadata["labels"])
            payload = {"title": item["title"], "description": item["description"], **metadata}
            filename = f"{key}.json"
            files[filename] = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()
            target = item["target"]
            collection = "projects" if item["type"] == "issue" else "groups"
            endpoint = f"{collection}/{target['id']}/{item['type']}s"
            command = api_command(urlsplit(target["url"]).netloc, endpoint, root / filename)
            lines.extend([code_block(command), ""])
    if plan["links"]:
        lines.extend([f"## {labels['links']}", ""])
    for index, link in enumerate(plan["links"]):
        source, target = items[link["source"]], items[link["target"]]
        lines.extend([f"- {source['title']} → {target['title']}: {link['rationale']}", ""])
        supported = (
            source["type"] == target["type"] == "issue"
            and ready(source)
            and ready(target)
            and urlsplit(source["target"]["url"]).netloc == urlsplit(target["target"]["url"]).netloc
        )
        if not supported or not link["verified"]:
            complete = False
            lines.extend([labels["unsupported"], ""])
        elif not source["existing_iid"] or not target["existing_iid"]:
            complete = False
            lines.extend([labels["deferred"], ""])
        else:
            payload = {
                "target_project_id": target["target"]["id"],
                "target_issue_iid": target["existing_iid"],
                "link_type": "is_blocked_by",
            }
            filename = f"link-{index + 1}.json"
            files[filename] = (json.dumps(payload, indent=2) + "\n").encode()
            endpoint = f"projects/{source['target']['id']}/issues/{source['existing_iid']}/links"
            command = api_command(
                urlsplit(source["target"]["url"]).netloc, endpoint, root / filename
            )
            lines.extend([code_block(command), ""])
    files["task-publication.md"] = ("\n".join(lines).rstrip() + "\n").encode()
    return files, complete


def write_bundle(root: Path, files: dict[str, bytes]) -> None:
    for parent in (root, *root.parents):
        if parent.is_symlink():
            raise WorkflowError("publication directory must not use symlinks")
    if root.exists():
        if not root.is_dir() or {p.name for p in root.iterdir()} != set(files):
            raise WorkflowError("publication directory already contains other work")
        for name, content in files.items():
            path = root / name
            if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
                raise WorkflowError("publication artifact changed; choose a new directory")
        return
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".task-publication-", dir=root.parent) as temporary:
        staged = Path(temporary) / "bundle"
        staged.mkdir(mode=0o700)
        for name, content in files.items():
            atomic_write(staged / name, content)
        os.rename(staged, root)


def run(argv: list[str] | None = None) -> int:
    cli = Parser(prog="task-publication")
    cli.add_argument("--capabilities", action="store_true")
    cli.add_argument("--input")
    cli.add_argument("--output-dir")
    try:
        args = cli.parse_args(argv)
        if args.capabilities:
            emit({"schema_version": 1, "mutation": "local", "external_mutations": False})
            return 0
        if not args.input:
            raise WorkflowError("--input is required")
        path = Path(args.input)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise WorkflowError("input must be a small regular non-symlink JSON file")
        plan = validate(json.loads(path.read_text(encoding="utf-8")))
        directory = args.output_dir or f".task-prepare/{digest(plan)[:20]}"
        root = output_path(f"{directory}/task-publication.md").parent
        files, complete = render(plan, root)
        write_bundle(root, files)
        emit(
            {
                "status": "ready" if complete else "partial",
                "output": str(root / "task-publication.md"),
                "items": len(plan["items"]),
                "external_mutations": False,
            }
        )
        return 0
    except (OSError, ValueError, TypeError) as exc:
        emit({"status": "error", "error": str(exc), "external_mutations": False})
        return 2
