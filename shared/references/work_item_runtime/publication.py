"""Render bounded, manual-only GitLab task plans from agent-assessed evidence."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from .contract import Parser, WorkflowError, atomic_write, digest, emit, output_path

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ..state_artifacts import render_mutation_command, versioned_markdown, xdg_state_home
else:
    try:
        from ..state_artifacts import render_mutation_command, versioned_markdown, xdg_state_home
    except ImportError:
        from .state_artifacts import render_mutation_command, versioned_markdown, xdg_state_home

CHECKS = {"target", "templates", "metadata", "duplicates", "semantics"}
GRAPHQL_ENDPOINT = "../graphql"
WORK_ITEM_GID = re.compile(r"gid://gitlab/WorkItem/[1-9][0-9]*")
WORK_ITEM_TYPE_GID = re.compile(r"gid://gitlab/WorkItems::Type/[1-9][0-9]*")
TEXT = {
    "en": {
        "title": "Task publication plan",
        "manual": "Run commands manually after reviewing the text. Creation commands are not idempotent. GitLab GraphQL answers HTTP 200 with an errors field: inspect every response before retrying. Check GitLab before retrying. Keep this directory until publication is complete.",
        "ready": "Ready to create",
        "blocked": "Publication blocked",
        "existing": "Already exists: creation omitted",
        "checks": "Checks and open questions",
        "links": "Dependencies",
        "deferred": "Deferred: obtain and verify both real issue IIDs, then regenerate this plan. Do not repeat creation commands.",
        "unsupported": "Deferred: this relationship needs a verified API supported by the target instance.",
        "deferred_gid": "Deferred: record the observed work item ID of both items, then regenerate this plan.",
        "deferred_parent": "Deferred: create the parent item first, record its observed work item ID, then regenerate this plan.",
        "deferred_close": "Deferred: record the observed work item ID of this item, then regenerate this plan to close it.",
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
        "manual": "Выполни команды вручную после проверки текста. Команды создания не идемпотентны: перед повтором проверь GitLab. GitLab GraphQL отвечает HTTP 200 с полем errors: проверь ответ каждой команды перед повтором. Сохрани эту директорию до завершения публикации.",
        "ready": "Готово к созданию",
        "blocked": "Публикация заблокирована",
        "existing": "Уже существует: команда создания не нужна",
        "checks": "Проверки и открытые вопросы",
        "links": "Зависимости",
        "deferred": "Отложено: получи и проверь реальные IID обеих задач, затем обнови план. Не повторяй команды создания.",
        "unsupported": "Отложено: для этой связи нужно проверить API, поддерживаемое целевой инсталляцией.",
        "deferred_gid": "Отложено: зафиксируй наблюдаемые work item ID обеих задач, затем обнови план.",
        "deferred_parent": "Отложено: сначала создай родительскую задачу, зафиксируй её наблюдаемый work item ID, затем обнови план.",
        "deferred_close": "Отложено: зафиксируй наблюдаемый work item ID этой задачи, затем обнови план для закрытия.",
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

CREATE_ISSUE = """mutation CreateIssue($input: CreateIssueInput!) {
  createIssue(input: $input) {
    issue {
      iid
      webUrl
    }
    errors
  }
}"""

CREATE_EPIC = """mutation CreateEpic($input: CreateEpicInput!) {
  createEpic(input: $input) {
    epic {
      iid
      webUrl
    }
    errors
  }
}"""

UPDATE_ISSUE = """mutation UpdateIssue($input: UpdateIssueInput!) {
  updateIssue(input: $input) {
    issue {
      iid
    }
    errors
  }
}"""

CREATE_WORK_ITEM = """mutation WorkItemCreate($input: WorkItemCreateInput!) {
  workItemCreate(input: $input) {
    workItem {
      id
      iid
      webUrl
    }
    errors
  }
}"""

UPDATE_WORK_ITEM = """mutation WorkItemUpdate($input: WorkItemUpdateInput!) {
  workItemUpdate(input: $input) {
    workItem {
      id
      state
    }
    errors
  }
}"""

ADD_LINKED_ITEMS = """mutation WorkItemAddLinkedItems($input: WorkItemAddLinkedItemsInput!) {
  workItemAddLinkedItems(input: $input) {
    workItem {
      iid
    }
    errors
  }
}"""


def marker_helper() -> Path:
    sibling = Path(__file__).with_name("state_artifacts.py")
    return sibling if sibling.exists() else Path(__file__).parents[1] / "state_artifacts.py"


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


def validate_metadata(metadata: object, item_type: str, version: int) -> None:
    if not isinstance(metadata, dict) or set(metadata) - {
        "labels",
        "label_ids",
        "assignee_ids",
        "milestone_id",
        "confidential",
    }:
        raise WorkflowError("unsupported metadata")
    if item_type == "epic" and set(metadata) - {"labels", "label_ids", "confidential"}:
        raise WorkflowError("epic metadata supports only labels and confidentiality")
    if "labels" in metadata and (
        not isinstance(metadata["labels"], list)
        or not all(text(label) and "," not in label for label in metadata["labels"])
    ):
        raise WorkflowError("labels must be observed names without commas")
    if "label_ids" in metadata and (
        not isinstance(metadata["label_ids"], list)
        or not all(positive(identifier) for identifier in metadata["label_ids"])
    ):
        raise WorkflowError("label_ids must be observed numeric IDs")
    if version == 2 and "label_ids" in metadata:
        raise WorkflowError("label_ids requires publication version 3")
    if version == 3:
        if ("labels" in metadata) != ("label_ids" in metadata):
            raise WorkflowError("labels and label_ids must be supplied together")
        if "labels" in metadata and len(metadata["labels"]) != len(metadata["label_ids"]):
            raise WorkflowError("labels and label_ids must describe the same labels")
    if "assignee_ids" in metadata and (
        not isinstance(metadata["assignee_ids"], list)
        or not all(positive(identifier) for identifier in metadata["assignee_ids"])
    ):
        raise WorkflowError("assignees must be observed numeric IDs")
    if "milestone_id" in metadata and not positive(metadata["milestone_id"]):
        raise WorkflowError("milestone_id must be an observed numeric ID")
    if "confidential" in metadata and type(metadata["confidential"]) is not bool:
        raise WorkflowError("confidential must be boolean")


def validate(value: object) -> dict[str, Any]:
    plan = fields(
        value,
        {"version", "plan_key", "locale", "batch_agreement", "items", "links"},
        "plan",
    )
    version = plan["version"]
    if version not in (2, 3) or plan["locale"] not in TEXT:
        raise WorkflowError("unsupported publication version or locale")
    if not isinstance(plan["plan_key"], str) or not re.fullmatch(
        r"[a-z][a-z0-9-]{0,63}", plan["plan_key"]
    ):
        raise WorkflowError("plan_key must be a safe lowercase identifier")
    items = plan["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= 50:
        raise WorkflowError("plan requires 1 to 50 items")
    if not isinstance(plan["batch_agreement"], str) or (
        len(items) > 1 and not text(plan["batch_agreement"])
    ):
        raise WorkflowError("multiple items require the user's batch agreement")
    base_fields = {
        "key",
        "title",
        "description",
        "target",
        "type",
        "metadata",
        "checks",
        "existing_iid",
    }
    item_fields = base_fields | {"work_item_id"}
    if version == 3:
        item_fields = item_fields | {"parent", "initial_state", "work_item_type_id"}
    types = {"issue", "epic"} if version == 2 else {"issue", "task", "epic"}
    ids: set[str] = set()
    parsed: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict) or (
            set(raw) != item_fields and not (version == 2 and set(raw) == base_fields)
        ):
            raise WorkflowError(
                f"item: expected fields {', '.join(sorted(item_fields))} for version {version}"
            )
        item = raw
        key = item["key"]
        if isinstance(key, str) and (key == "task-publication" or re.fullmatch(r"link-\d+", key)):
            raise WorkflowError("item key conflicts with a reserved artifact name")
        if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", key) or key in ids:
            raise WorkflowError("item keys must be unique safe identifiers")
        ids.add(key)
        if not text(item["title"]) or any(c in item["title"] for c in "\r\n"):
            raise WorkflowError("item title must be one nonempty line")
        if not text(item["description"]) or item["type"] not in types:
            raise WorkflowError(f"item requires a description and one of {sorted(types)} type")
        validate_target(item["target"])
        target = item["target"]
        if target is not None and (item["type"] != "epic") != (target["kind"] == "project"):
            raise WorkflowError("issues and tasks require projects; epics require groups")
        if item["existing_iid"] is not None and not positive(item["existing_iid"]):
            raise WorkflowError("existing_iid must be an observed positive IID or null")
        if item.get("work_item_id") is not None and (
            not isinstance(item["work_item_id"], str)
            or WORK_ITEM_GID.fullmatch(item["work_item_id"]) is None
        ):
            raise WorkflowError(
                "work_item_id must be an observed gid://gitlab/WorkItem/<id> or null"
            )
        if version == 3:
            if item["initial_state"] not in ("open", "closed"):
                raise WorkflowError("initial_state must be open or closed")
            if item["work_item_type_id"] is not None and (
                not isinstance(item["work_item_type_id"], str)
                or WORK_ITEM_TYPE_GID.fullmatch(item["work_item_type_id"]) is None
            ):
                raise WorkflowError(
                    "work_item_type_id must be an observed gid://gitlab/WorkItems::Type/<id> or null"
                )
        checks = fields(item["checks"], CHECKS, "checks")
        for raw_check in checks.values():
            checked = fields(raw_check, {"status", "detail"}, "check")
            if checked["status"] not in ("verified", "blocked") or not text(checked["detail"]):
                raise WorkflowError("checks require verified/blocked status and evidence detail")
        validate_metadata(item["metadata"], item["type"], version)
        if (
            version == 2
            and item["type"] == "issue"
            and item["target"] is not None
            and all(check["status"] == "verified" for check in checks.values())
            and "milestone_id" not in item["metadata"]
        ):
            raise WorkflowError("a ready version 2 issue requires an observed milestone_id")
        if (
            version == 3
            and item["target"] is not None
            and item["existing_iid"] is None
            and item["work_item_type_id"] is None
            and all(check["status"] == "verified" for check in checks.values())
        ):
            raise WorkflowError("a ready version 3 creation requires an observed work_item_type_id")
        parsed.append(item)
    parents: dict[str, str] = {}
    for item in parsed:
        parent = item.get("parent")
        if parent is None:
            continue
        if not isinstance(parent, str) or parent == item["key"] or parent not in ids:
            raise WorkflowError("parent must reference another item key in this plan")
        if item["type"] != "task":
            raise WorkflowError("parent is supported only for task items")
        parent_item = next(candidate for candidate in parsed if candidate["key"] == parent)
        if parent_item["type"] not in ("issue", "task"):
            raise WorkflowError("parent must be an issue or task item")
        if (
            item["target"] is not None
            and parent_item["target"] is not None
            and urlsplit(item["target"]["url"]).netloc
            != urlsplit(parent_item["target"]["url"]).netloc
        ):
            raise WorkflowError("parent and child must target one GitLab host")
        parents[item["key"]] = parent
    if not isinstance(plan["links"], list):
        raise WorkflowError("links must be a list")
    edges: dict[str, list[str]] = {key: [] for key in ids}
    seen: set[tuple[str, str]] = set()
    for key, parent in parents.items():
        edges[parent].append(key)
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


def user_gid(identifier: int) -> str:
    return f"gid://gitlab/User/{identifier}"


def milestone_gid(identifier: int) -> str:
    return f"gid://gitlab/Milestone/{identifier}"


def label_gid(identifier: int) -> str:
    return f"gid://gitlab/Label/{identifier}"


def namespace_path(target: dict[str, Any]) -> str:
    path = urlsplit(target["url"]).path
    if target["kind"] == "group":
        path = path.removeprefix("/groups")
    return str(path.lstrip("/"))


def api_command(
    host: str,
    endpoint: str,
    payload: Path,
    *,
    action: str,
    binding: str,
    method: str = "POST",
) -> str:
    argv = [
        "glab",
        "api",
        "--hostname",
        host,
        "--method",
        method,
        endpoint,
        "--header",
        "Content-Type: application/json",
        "--input",
        str(payload),
    ]
    return render_mutation_command(
        argv,
        skill="task-prepare",
        action=action,
        binding=binding,
        helper=marker_helper(),
    )


def request_payload(query: str, variables: dict[str, Any]) -> bytes:
    return (
        json.dumps({"query": query, "variables": variables}, ensure_ascii=False, indent=2) + "\n"
    ).encode()


def code_block(command: str) -> str:
    fence = "`" * max(3, max((len(s) + 1 for s in re.findall(r"`+", command)), default=3))
    return f"{fence}sh\n{command}\n{fence}"


def create_issue_variables(item: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    metadata = item["metadata"]
    value: dict[str, Any] = {
        "projectPath": namespace_path(target),
        "title": item["title"],
        "description": item["description"],
    }
    if metadata.get("labels"):
        value["labels"] = metadata["labels"]
    if metadata.get("milestone_id"):
        value["milestoneId"] = milestone_gid(metadata["milestone_id"])
    if metadata.get("assignee_ids"):
        value["assigneeIds"] = [user_gid(i) for i in metadata["assignee_ids"]]
    if "confidential" in metadata:
        value["confidential"] = metadata["confidential"]
    return value


def create_epic_variables(item: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    metadata = item["metadata"]
    value: dict[str, Any] = {
        "groupPath": namespace_path(target),
        "title": item["title"],
        "description": item["description"],
    }
    if metadata.get("labels"):
        value["addLabels"] = metadata["labels"]
    if "confidential" in metadata:
        value["confidential"] = metadata["confidential"]
    return value


def create_work_item_variables(
    item: dict[str, Any], target: dict[str, Any], parent_id: str | None
) -> dict[str, Any]:
    metadata = item["metadata"]
    value: dict[str, Any] = {
        "namespacePath": namespace_path(target),
        "workItemTypeId": item["work_item_type_id"],
        "title": item["title"],
        "description": item["description"],
    }
    if metadata.get("label_ids"):
        value["labelsWidget"] = {"labelIds": [label_gid(i) for i in metadata["label_ids"]]}
    if metadata.get("assignee_ids"):
        value["assigneesWidget"] = {"assigneeIds": [user_gid(i) for i in metadata["assignee_ids"]]}
    if metadata.get("milestone_id"):
        value["milestoneWidget"] = {"milestoneId": milestone_gid(metadata["milestone_id"])}
    if "confidential" in metadata:
        value["confidential"] = metadata["confidential"]
    if parent_id is not None:
        value["hierarchyWidget"] = {"parentId": parent_id}
    return {"input": value}


def render(plan: dict[str, Any], root: Path) -> tuple[dict[str, bytes], bool]:
    labels = TEXT[plan["locale"]]
    lines = [f"# {labels['title']}", "", labels["manual"], ""]
    files: dict[str, bytes] = {}
    binding = digest(plan)
    content_prefix = f".task-publication/{binding}"
    content_root = root / content_prefix
    complete = True
    items = {item["key"]: item for item in plan["items"]}
    version = plan["version"]
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
        files[f"{content_prefix}/{key}.md"] = item["description"].encode()
        target = item["target"]
        host = str(urlsplit(target["url"]).netloc) if target is not None else ""
        if is_ready and item["existing_iid"] is None:
            parent_id = None
            parent = item.get("parent")
            if parent is not None and items[parent].get("work_item_id") is None:
                complete = False
                lines.extend([labels["deferred_parent"], ""])
                continue
            if parent is not None:
                parent_id = items[parent]["work_item_id"]
            if version == 2 and item["type"] == "issue":
                payload = request_payload(
                    CREATE_ISSUE, {"input": create_issue_variables(item, target)}
                )
                filename = f"{key}.json"
                files[f"{content_prefix}/{filename}"] = payload
                command = api_command(
                    host,
                    GRAPHQL_ENDPOINT,
                    content_root / filename,
                    action=f"item:{key}:create",
                    binding=binding,
                )
                lines.extend([code_block(command), ""])
            elif version == 2 and item["type"] == "epic":
                payload = request_payload(
                    CREATE_EPIC, {"input": create_epic_variables(item, target)}
                )
                filename = f"{key}.json"
                files[f"{content_prefix}/{filename}"] = payload
                command = api_command(
                    host,
                    GRAPHQL_ENDPOINT,
                    content_root / filename,
                    action=f"item:{key}:create",
                    binding=binding,
                )
                lines.extend([code_block(command), ""])
            else:
                payload = request_payload(
                    CREATE_WORK_ITEM, create_work_item_variables(item, target, parent_id)
                )
                filename = f"{key}.json"
                files[f"{content_prefix}/{filename}"] = payload
                command = api_command(
                    host,
                    GRAPHQL_ENDPOINT,
                    content_root / filename,
                    action=f"item:{key}:create",
                    binding=binding,
                )
                lines.extend([code_block(command), ""])
            if item.get("initial_state") == "closed":
                complete = False
                lines.extend([labels["deferred_close"], ""])
        elif is_ready:
            metadata = item["metadata"]
            if item["type"] == "issue" and "milestone_id" in metadata:
                variables: dict[str, Any] = {
                    "input": {
                        "projectPath": namespace_path(target),
                        "iid": str(item["existing_iid"]),
                        "milestoneId": milestone_gid(metadata["milestone_id"]),
                    }
                }
                payload = request_payload(UPDATE_ISSUE, variables)
                filename = f"{key}-milestone.json"
                files[f"{content_prefix}/{filename}"] = payload
                command = api_command(
                    host,
                    GRAPHQL_ENDPOINT,
                    content_root / filename,
                    action=f"item:{key}:milestone",
                    binding=binding,
                )
                lines.extend([code_block(command), ""])
            elif item["type"] != "issue" and "milestone_id" in metadata:
                if item["work_item_id"] is None:
                    complete = False
                    lines.extend([labels["deferred_gid"], ""])
                else:
                    variables = {
                        "input": {
                            "id": item["work_item_id"],
                            "milestoneWidget": {
                                "milestoneId": milestone_gid(metadata["milestone_id"])
                            },
                        }
                    }
                    payload = request_payload(UPDATE_WORK_ITEM, variables)
                    filename = f"{key}-milestone.json"
                    files[f"{content_prefix}/{filename}"] = payload
                    command = api_command(
                        host,
                        GRAPHQL_ENDPOINT,
                        content_root / filename,
                        action=f"item:{key}:milestone",
                        binding=binding,
                    )
                    lines.extend([code_block(command), ""])
            if item.get("initial_state") == "closed":
                if item["work_item_id"] is None:
                    complete = False
                    lines.extend([labels["deferred_close"], ""])
                else:
                    variables = {"input": {"id": item["work_item_id"], "stateEvent": "CLOSE"}}
                    payload = request_payload(UPDATE_WORK_ITEM, variables)
                    filename = f"{key}-close.json"
                    files[f"{content_prefix}/{filename}"] = payload
                    command = api_command(
                        host,
                        GRAPHQL_ENDPOINT,
                        content_root / filename,
                        action=f"item:{key}:close",
                        binding=binding,
                    )
                    lines.extend([code_block(command), ""])
    if plan["links"]:
        lines.extend([f"## {labels['links']}", ""])
    linkable = {"issue"} if version == 2 else {"issue", "task"}
    for index, link in enumerate(plan["links"]):
        source, target_item = items[link["source"]], items[link["target"]]
        lines.extend([f"- {source['title']} → {target_item['title']}: {link['rationale']}", ""])
        supported = (
            source["type"] in linkable
            and target_item["type"] in linkable
            and ready(source)
            and ready(target_item)
            and urlsplit(source["target"]["url"]).netloc
            == urlsplit(target_item["target"]["url"]).netloc
        )
        if not supported or not link["verified"]:
            complete = False
            lines.extend([labels["unsupported"], ""])
        elif not source["existing_iid"] or not target_item["existing_iid"]:
            complete = False
            lines.extend([labels["deferred"], ""])
        elif source.get("work_item_id") is None or target_item.get("work_item_id") is None:
            complete = False
            lines.extend([labels["deferred_gid"], ""])
        else:
            variables = {
                "input": {
                    "id": source["work_item_id"],
                    "workItemsIds": [target_item["work_item_id"]],
                    "linkType": "BLOCKED_BY",
                }
            }
            filename = f"link-{index + 1}.json"
            files[f"{content_prefix}/{filename}"] = request_payload(ADD_LINKED_ITEMS, variables)
            command = api_command(
                urlsplit(source["target"]["url"]).netloc,
                GRAPHQL_ENDPOINT,
                content_root / filename,
                action=f"link:{index + 1}",
                binding=binding,
            )
            lines.extend([code_block(command), ""])
    files["task-publication.md"] = ("\n".join(lines).rstrip() + "\n").encode()
    return files, complete


def validate_bundle_path(root: Path) -> None:
    for parent in (root, *root.parents):
        if parent.is_symlink():
            raise WorkflowError("publication directory must not use symlinks")
    if root.exists():
        if not root.is_dir():
            raise WorkflowError("publication path must be a directory")
        for path in root.iterdir():
            if path.name == "task-publication.md":
                if path.is_symlink() or not path.is_file():
                    raise WorkflowError("publication plan must be a regular file")
            elif path.name in {".task-publication", "history"}:
                if path.is_symlink() or not path.is_dir():
                    raise WorkflowError("publication content path must be a directory")
            else:
                raise WorkflowError("publication directory contains an unexpected artifact")


def split_bundle(files: dict[str, bytes]) -> tuple[str, dict[str, bytes], bytes]:
    try:
        markdown = files["task-publication.md"]
    except KeyError as exc:
        raise WorkflowError("publication bundle requires task-publication.md") from exc
    support: dict[str, bytes] = {}
    content_id: str | None = None
    for name, content in files.items():
        if name == "task-publication.md":
            continue
        parts = Path(name).parts
        if (
            len(parts) != 3
            or parts[0] != ".task-publication"
            or not re.fullmatch(r"[0-9a-f]{64}", parts[1])
            or not re.fullmatch(r"(?:[a-z][a-z0-9-]{0,63}|link-[1-9][0-9]*)\.(?:md|json)", parts[2])
        ):
            raise WorkflowError("publication bundle contains an unsafe support path")
        if content_id is not None and content_id != parts[1]:
            raise WorkflowError("publication bundle must use one content directory")
        content_id = parts[1]
        support[parts[2]] = content
    if content_id is None or not support:
        raise WorkflowError("publication bundle requires immutable support files")
    return content_id, support, markdown


def validate_content(path: Path, files: dict[str, bytes]) -> None:
    if path.is_symlink() or not path.is_dir():
        raise WorkflowError("publication content path must be a regular directory")
    if {item.name for item in path.iterdir()} != set(files):
        raise WorkflowError("immutable publication content does not match its address")
    for name, content in files.items():
        artifact = path / name
        if artifact.is_symlink() or not artifact.is_file() or artifact.read_bytes() != content:
            raise WorkflowError("immutable publication content was changed")


@contextmanager
def slot_lock(root: Path) -> Iterator[None]:
    lock = root.with_name(f".{root.name}.task-publication.lock")
    if lock.is_symlink():
        raise WorkflowError("publication lock must not be a symlink")
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise WorkflowError("another publication update holds this slot lock") from exc
    try:
        yield
    finally:
        lock.rmdir()


def write_bundle(root: Path, files: dict[str, bytes], *, legacy: bytes | None = None) -> None:
    content_id, support, markdown = split_bundle(files)
    validate_bundle_path(root)
    root.parent.mkdir(parents=True, exist_ok=True)
    validate_bundle_path(root)
    with slot_lock(root):
        validate_bundle_path(root)
        root.mkdir(mode=0o700, exist_ok=True)
        internal = root / ".task-publication"
        if internal.is_symlink():
            raise WorkflowError("publication content path must not be a symlink")
        internal.mkdir(mode=0o700, exist_ok=True)
        if internal.is_symlink() or not internal.is_dir():
            raise WorkflowError("publication content path must be a regular directory")
        content_root = internal / content_id
        if content_root.exists() or content_root.is_symlink():
            validate_content(content_root, support)
        else:
            staged = Path(tempfile.mkdtemp(prefix=f".{content_id}.stage-", dir=internal))
            try:
                for name, content in support.items():
                    atomic_write(staged / name, content)
                validate_content(staged, support)
                try:
                    os.rename(staged, content_root)
                except FileExistsError:
                    validate_content(content_root, support)
            finally:
                shutil.rmtree(staged, ignore_errors=True)
            validate_content(content_root, support)
        plan_path = root / "task-publication.md"
        if plan_path.is_symlink() or (plan_path.exists() and not plan_path.is_file()):
            raise WorkflowError("publication plan must be a regular file")
        stable_markdown = versioned_markdown(plan_path, markdown, legacy=legacy)
        if plan_path.exists() and plan_path.read_bytes() == stable_markdown:
            return
        atomic_write(plan_path, stable_markdown)


def default_root(plan_key: str) -> Path:
    workspace = Path.cwd().resolve(strict=True)
    workspace_id = digest({"workspace": os.fsdecode(os.fsencode(workspace))})
    return xdg_state_home() / "agent-skills" / "task-prepare" / workspace_id / plan_key


def run(argv: list[str] | None = None) -> int:
    cli = Parser(prog="task-publication")
    cli.add_argument("--capabilities", action="store_true")
    cli.add_argument("--input")
    cli.add_argument("--output-dir")
    try:
        args = cli.parse_args(argv)
        if args.capabilities:
            emit(
                {
                    "schema_version": 1,
                    "publication_version": 3,
                    "input_versions": [2, 3],
                    "mutation": "local",
                    "external_mutations": False,
                }
            )
            return 0
        if not args.input:
            raise WorkflowError("--input is required")
        path = Path(args.input)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            raise WorkflowError("input must be a small regular non-symlink JSON file")
        plan = validate(json.loads(path.read_text(encoding="utf-8")))
        legacy = None
        if args.output_dir:
            root = output_path(f"{args.output_dir}/task-publication.md").parent
        else:
            root = default_root(plan["plan_key"])
            legacy_path = output_path(f".task-prepare/{plan['plan_key']}/task-publication.md")
            if legacy_path.exists() and not legacy_path.is_symlink() and legacy_path.is_file():
                legacy = legacy_path.read_bytes()
        files, complete = render(plan, root)
        write_bundle(root, files, legacy=legacy)
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
