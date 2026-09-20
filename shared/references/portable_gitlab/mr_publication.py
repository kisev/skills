"""Manual MR metadata plans, template discovery, and localized presentation."""

import base64
import binascii
import hashlib
import json
import shlex
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

from . import contract as portable
from .label_assessment import validate_label_assessments

CONTENT_FIELDS = {
    "locale",
    "title",
    "description",
    "change_summary",
    "limitations",
    "template",
    "preservation_notes",
    "label_assessments",
    "semver_impact",
    "semver_rationale",
}


@contextmanager
def publication_lock(root: Path) -> Iterator[None]:
    lock = root / ".mr-publication.lock"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise portable.WorkflowError("another MR publication update holds the lock") from exc
    try:
        yield
    finally:
        lock.rmdir()


def collect_templates(host: str, project: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"complete": True, "items": [], "errors": [], "revision": None}
    default = project.get("merge_requests_template")
    if default is not None and (not isinstance(default, str) or len(default.encode()) > 262144):
        result["complete"] = False
        result["errors"].append(
            "project default template is invalid or exceeds the collection bound"
        )
        return result
    if isinstance(default, str) and default.strip():
        result["items"].append(
            {"id": "project-default", "body": default, "source": "project", "default": True}
        )
    try:
        branch = project.get("default_branch")
        if not isinstance(branch, str) or not branch.strip():
            raise portable.WorkflowError("project default branch is unavailable")
        prefix = f"projects/{project['id']}/repository"
        commit = portable.glab_json(host, f"{prefix}/commits/{quote(branch, safe='')}")
        if not isinstance(commit, dict) or not portable.is_sha(commit.get("id")):
            raise portable.WorkflowError("template revision is unavailable")
        revision = commit["id"]
        result["revision"] = revision
        path = ""
        for directory in (".gitlab", "merge_request_templates", None):
            tree = portable.paginated(
                host, f"{prefix}/tree?ref={revision}&path={quote(path, safe='')}"
            )
            if not tree["complete"]:
                raise portable.WorkflowError("template directory listing is incomplete")
            entries = cast("list[object]", tree["items"])
            if not all(
                isinstance(item, dict)
                and isinstance(item.get("path"), str)
                and item.get("type") in {"tree", "blob", "commit"}
                for item in entries
            ):
                raise portable.WorkflowError("template directory listing is invalid")
            if directory is not None:
                expected = f"{path}/{directory}".lstrip("/")
                if not any(
                    isinstance(item, dict)
                    and item.get("path") == expected
                    and item.get("type") == "tree"
                    for item in entries
                ):
                    return result
                path = expected
                continue
            files = [
                item
                for item in entries
                if isinstance(item, dict)
                and item.get("type") == "blob"
                and isinstance(item.get("path"), str)
                and item["path"].endswith(".md")
            ]
            if len(files) > 50:
                raise portable.WorkflowError("template count exceeds the collection bound")
            size = 0
            for item in sorted(files, key=lambda value: value["path"]):
                file_path = item["path"]
                if Path(file_path).parent.as_posix() != path:
                    raise portable.WorkflowError("template path escapes its directory")
                data = portable.glab_json(
                    host, f"{prefix}/files/{quote(file_path, safe='')}?ref={revision}"
                )
                if (
                    not isinstance(data, dict)
                    or data.get("encoding") != "base64"
                    or data.get("file_path") != file_path
                ):
                    raise portable.WorkflowError("template file response is invalid")
                body = base64.b64decode(data["content"], validate=True).decode("utf-8")
                size += len(body.encode())
                if size > 262144:
                    raise portable.WorkflowError("template content exceeds the collection bound")
                result["items"].append(
                    {
                        "id": file_path,
                        "body": body,
                        "source": f"{project['id']}:{revision}:{file_path}",
                        "default": Path(file_path).name == "Default.md",
                    }
                )
    except (
        portable.WorkflowError,
        KeyError,
        TypeError,
        ValueError,
        UnicodeError,
        binascii.Error,
    ) as exc:
        result["complete"] = False
        result["errors"].append(str(exc))
    return result


def validate_content(
    bundle: dict[str, Any], value: object
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(value, dict) or set(value) != CONTENT_FIELDS:
        raise portable.WorkflowError(
            "MR content contract changed; prepare a fresh draft with locale, template, preservation notes and exhaustive label assessments"
        )
    content = value
    locale = bundle["project"].get("locale", "en")
    if content["locale"] not in ("en", "ru") or content["locale"] != locale:
        raise portable.WorkflowError("MR content locale does not match the prepared locale")
    for field in ("title", "description", "semver_rationale"):
        if not portable.nonempty_string(content[field]):
            raise portable.WorkflowError(f"MR {field} must be non-empty")
    if any(character in content["title"] for character in "\r\n"):
        raise portable.WorkflowError("MR title must be one line")
    for field in ("change_summary", "limitations", "preservation_notes"):
        if not isinstance(content[field], list) or not all(
            portable.nonempty_string(item) for item in content[field]
        ):
            raise portable.WorkflowError(f"MR {field} must contain non-empty strings")
    if not 1 <= len(content["change_summary"]) <= 4 or not content["preservation_notes"]:
        raise portable.WorkflowError(
            "MR draft needs a concise change summary and a preservation assessment"
        )
    if content["semver_impact"] not in ("major", "minor", "patch", "none", "not_applicable"):
        raise portable.WorkflowError("MR SemVer assessment is invalid")
    selection = portable.exact_keys(content["template"], {"id", "rationale"}, "template selection")
    if not portable.nonempty_string(selection["rationale"]):
        raise portable.WorkflowError("template selection needs a rationale")
    if selection["id"] is not None and not isinstance(selection["id"], str):
        raise portable.WorkflowError("template selection ID must be a string or null")
    templates = bundle["project"].get("mr_templates")
    if not isinstance(templates, dict):
        raise portable.WorkflowError("template evidence is missing; prepare the MR again")
    ids = {item["id"] for item in templates["items"]}
    if (ids and selection["id"] not in ids) or (not ids and selection["id"] is not None):
        raise portable.WorkflowError(
            "select one collected MR template, or null only when none is available"
        )
    if selection["id"] is not None:
        template = next(item for item in templates["items"] if item["id"] == selection["id"])
        headings = portable.template_headings(template["body"])
        if not all(heading in content["description"].splitlines() for heading in headings):
            raise portable.WorkflowError(
                "MR description does not preserve selected template headings"
            )
    if not templates["complete"] and not content["limitations"]:
        raise portable.WorkflowError("unavailable templates must be reported as a limitation")
    labels = validate_label_assessments(
        bundle, content["label_assessments"], content["semver_impact"]
    )
    return content, labels


def text(locale: str) -> dict[str, str]:
    if locale == "ru":
        return {
            "heading": "План обновления MR",
            "context": "Контекст",
            "changes": "Что изменилось",
            "compatibility": "Совместимость и миграция",
            "verification": "Проверки",
            "references": "Ссылки",
            "warning": "Команды подготовлены для ручного запуска. Ничего не опубликовано.",
            "summary": "TL;DR правок",
            "title": "Заголовок",
            "description": "Описание",
            "labels": "Лейблы",
            "keep": "Изменение не требуется.",
            "add": "Добавить",
            "remove": "Убрать",
            "limitations": "Ограничения",
            "checks": "Проверки",
            "pipeline": "Pipeline текущей ревизии",
            "finalize": "Перед публикацией проверь актуальность плана:",
            "complete": "Сбор основных данных завершён.",
            "partial": "Сбор данных неполон. Публикация заблокирована.",
            "templates": "Шаблоны не удалось полностью получить. Это не означает, что их нет.",
            "ready": "Подготовлен план обновления MR.",
            "blocked": "Подготовка MR заблокирована.",
            "path": "План обновления",
        }
    return {
        "heading": "MR update plan",
        "context": "Context",
        "changes": "Changes",
        "compatibility": "Compatibility and migration",
        "verification": "Verification",
        "references": "References",
        "warning": "Commands are for manual execution. Nothing was published.",
        "summary": "TL;DR of metadata changes",
        "title": "Title",
        "description": "Description",
        "labels": "Labels",
        "keep": "No change needed.",
        "add": "Add",
        "remove": "Remove",
        "limitations": "Limitations",
        "checks": "Checks",
        "pipeline": "Pipeline for the current revision",
        "finalize": "Check plan freshness before publication:",
        "complete": "Core evidence collection is complete.",
        "partial": "Evidence collection is incomplete. Publication is blocked.",
        "templates": "Template retrieval is incomplete. This does not mean no templates exist.",
        "ready": "Prepared an MR update plan.",
        "blocked": "MR preparation is blocked.",
        "path": "Update plan",
    }


def blocked_chat(locale: str, reason: str) -> str:
    if locale == "ru":
        if "locale" in reason:
            detail = "Язык черновика не совпадает с языком подготовки."
        elif "template" in reason:
            detail = "Не удалось подтвердить шаблон или его выбор."
        elif "label" in reason or "SemVer" in reason:
            detail = "Оценка лейблов или совместимости неполна либо противоречива."
        elif "lock" in reason:
            detail = "Файл результата занят другим запуском."
        elif any(
            word in reason
            for word in ("match", "modified", "superseded", "stale", "companion", "pointer")
        ):
            detail = "План изменён, устарел или не соответствует связанным файлам."
        elif "legacy" in reason or "contract changed" in reason:
            detail = "Формат плана или черновика устарел."
        elif "requires" in reason or "must" in reason or "needs" in reason:
            detail = "В черновике отсутствуют обязательные данные или нарушен их формат."
        else:
            detail = "Не удалось подтвердить входные данные или завершить текущий этап."
        return f"Подготовка MR заблокирована. {detail} Исправь причину и повтори подготовку для точного URL MR."
    return f"MR preparation is blocked. {reason}. Correct the problem and prepare the exact MR URL again."


def freshness_chat(locale: str, result: dict[str, Any]) -> str:
    if result["status"] == "ok":
        return (
            "Актуальность плана проверена. Ничего не опубликовано."
            if locale == "ru"
            else "Plan freshness checked. Nothing was published."
        )
    names = {
        "mr_project": "шаблоны или настройки проекта",
        "object": "метаданные MR",
        "labels": "каталог лейблов",
        "discussions": "обсуждения",
        "changed_files": "diff",
        "commits": "коммиты",
        "pipelines": "pipeline",
        "head_sha": "текущая ревизия",
        "base_sha": "базовая ревизия",
        "start_sha": "начальная ревизия",
        "retrieval_complete": "полнота сбора",
    }
    changes = ", ".join(
        names.get(item, item) if locale == "ru" else item for item in result.get("changed", [])
    )
    if locale == "ru":
        detail = f"Изменились: {changes}." if changes else "Сбор данных неполон."
        return f"План обновления MR устарел. {detail} Повтори подготовку перед публикацией."
    detail = f"Changed: {changes}." if changes else "Evidence collection is incomplete."
    return f"The MR update plan is stale. {detail} Prepare it again before publication."


def request_specs(
    root: Path, bundle: dict[str, Any], content: dict[str, Any], labels: dict[str, Any]
) -> list[dict[str, str]]:
    requests: list[tuple[str, dict[str, Any]]] = []
    for field in ("title", "description"):
        if (bundle["object"].get(field) or "") != content[field]:
            requests.append((field, {field: content[field]}))
    delta = {
        f"{action}_labels": ",".join(labels[action])
        for action in ("add", "remove")
        if labels[action]
    }
    if delta:
        if any("," in name for action in ("add", "remove") for name in labels[action]):
            raise portable.WorkflowError(
                "GitLab comma-separated label updates cannot represent a label containing a comma"
            )
        requests.append(("labels", delta))
    result: list[dict[str, str]] = []
    target = bundle["target"]
    endpoint = f"projects/{target['project_id']}/merge_requests/{target['iid']}"
    for field, payload in requests:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
        digest = hashlib.sha256(body.encode()).hexdigest()
        name = f"{digest}-{field}.json"
        path = root / "artifacts" / "mr_requests" / name
        command = shlex.join(
            [
                "glab",
                "api",
                "--hostname",
                target["hostname"],
                "--method",
                "PUT",
                endpoint,
                "--header",
                "Content-Type: application/json",
                "--input",
                str(path),
            ]
        )
        result.append(
            {"name": name, "content": body, "sha256": digest, "field": field, "command": command}
        )
    return result


def markdown(
    bundle: dict[str, Any],
    content: dict[str, Any],
    labels: dict[str, Any],
    requests: list[dict[str, str]],
    complete: bool,
) -> str:
    locale = content["locale"]
    words = text(locale)
    commands = {item["field"]: item["command"] for item in requests}
    lines = [
        f"# {words['heading']}",
        "",
        f"MR: {bundle['target']['url']}",
        "",
        words["warning"],
        "",
        f"## {words['summary']}",
        "",
        *[f"- {item}" for item in content["change_summary"]],
    ]
    for field in ("title", "description"):
        lines.extend(["", f"## {words[field]}", ""])
        if field not in commands:
            lines.append(words["keep"])
        else:
            lines.append(content[field])
            if complete:
                lines.extend(["", "```sh", commands[field], "```"])
    lines.extend(["", f"## {words['labels']}", ""])
    rationales = {item["name"]: item["rationale"] for item in labels["assessments"]}
    for action in ("add", "remove"):
        for name in labels[action]:
            lines.append(f"- {words[action]} `{name}`: {rationales[name]}")
    if "labels" not in commands:
        lines.append(words["keep"])
    elif complete:
        lines.extend(["", "```sh", commands["labels"], "```"])
    status, _ = portable.pipeline_summary(bundle)
    if locale == "ru":
        status = {
            "success": "успешен",
            "running": "выполняется",
            "failed": "завершился с ошибкой",
            "canceled": "отменён",
            "missing": "отсутствует",
        }.get(status, "не подтверждён")
    lines.extend(
        [
            "",
            f"## {words['checks']}",
            "",
            words["complete"] if complete else words["partial"],
            f"{words['pipeline']}: {status}.",
        ]
    )
    limitations = list(content["limitations"])
    if not bundle["project"]["mr_templates"]["complete"]:
        limitations.insert(0, words["templates"])
    if limitations:
        lines.extend(["", f"## {words['limitations']}", "", *[f"- {item}" for item in limitations]])
    return "\n".join(lines) + "\n"


def scaffold(source: Path, bundle: dict[str, Any], content_value: object) -> dict[str, Any]:
    root = portable.artifact_root(Path(bundle["artifact_root"]))
    try:
        with publication_lock(root):
            return scaffold_locked(source, bundle, content_value)
    except OSError as exc:
        raise portable.WorkflowError("MR publication files could not be written") from exc


def scaffold_locked(source: Path, bundle: dict[str, Any], content_value: object) -> dict[str, Any]:
    content, labels = validate_content(bundle, content_value)
    root = portable.artifact_root(Path(bundle["artifact_root"]))
    complete = bundle["retrieval_complete"] is True
    requests = request_specs(root, bundle, content, labels)
    portable.private_directory(root / "artifacts" / "mr_requests")
    for request in requests:
        portable.write_companion(
            root / "artifacts" / "mr_requests" / request["name"], request["content"]
        )
    body = markdown(bundle, content, labels, requests, complete)
    evidence_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    binding = plan_binding(evidence_digest, content, requests)
    # Bind the command as well as the document: an old editor tab must not check a newer plan.
    runner = Path(sys.argv[0]).resolve()
    finalize_command = shlex.join(
        [
            sys.executable,
            str(runner),
            "finalize",
            "--plan",
            str(root / "mr-publication.json"),
            "--expected-binding",
            binding,
        ]
    )
    body += (
        "\n" + text(content["locale"])["finalize"] + "\n\n```sh\n" + finalize_command + "\n```\n"
    )
    payload = {
        "profile": "mr-prepare",
        "external_mutations": False,
        "target": bundle["target"],
        "evidence_digest": evidence_digest,
        "complete": complete,
        "markdown": body,
        "plan_name": "mr-publication.md",
        "mr_content": content,
        "label_review": labels,
        "requests": requests,
    }
    path, digest = portable.write_artifact(root, "publication_plan", payload)
    portable.write_companion(path.with_suffix(".md"), body)
    if complete:
        # The stable document and pointer are updated together with rollback.
        destinations = [root / "mr-publication.md", root / "mr-publication.json"]
        if any(item.is_symlink() for item in destinations):
            raise portable.WorkflowError("stable MR publication paths must not be symlinks")
        previous = [item.read_bytes() if item.exists() else None for item in destinations]
        try:
            portable.write_json(destinations[1], {"plan_path": str(path), "digest": digest})
            portable.write_bytes(destinations[0], body.encode())
        except BaseException:
            for destination, old in zip(destinations, previous, strict=True):
                if old is None:
                    destination.unlink(missing_ok=True)
                else:
                    portable.write_bytes(destination, old)
            raise
    words = text(content["locale"])
    return {
        "status": "ok" if complete else "incomplete",
        "artifact_path": str(path),
        "digest": digest,
        "markdown_path": str(root / "mr-publication.md") if complete else None,
        "chat": (words["ready"] + f"\n\n{words['path']}: `{root / 'mr-publication.md'}`")
        if complete
        else words["blocked"] + " " + words["partial"],
        "external_mutations": False,
    }


def resolve_plan(path: Path) -> Path:
    if path.name != "mr-publication.json":
        return path
    pointer = portable.read_json(
        portable.regular_file(path, "MR publication pointer"), "MR publication pointer"
    )
    digest = pointer.get("digest")
    if not portable.is_digest(digest):
        raise portable.WorkflowError("MR publication pointer is invalid")
    expected = path.parent / "artifacts" / "publication_plan" / f"{digest}.json"
    if pointer.get("plan_path") != str(expected):
        raise portable.WorkflowError("MR publication pointer escapes its collection")
    return expected


def plan_binding(
    evidence_digest: str, content: dict[str, Any], requests: list[dict[str, str]]
) -> str:
    return portable.digest(
        {"evidence_digest": evidence_digest, "content": content, "requests": requests}
    )


def validate_plan(root: Path, plan: dict[str, Any], baseline: dict[str, Any]) -> None:
    content, labels = validate_content(baseline, plan["mr_content"])
    if labels != plan["label_review"]:
        raise portable.WorkflowError("MR label assessment does not match the evidence")
    if request_specs(root, baseline, content, labels) != plan["requests"]:
        raise portable.WorkflowError("MR request commands do not match the evidence and preview")
    stable = portable.regular_file(root / "mr-publication.md", "stable MR publication")
    if stable.read_text(encoding="utf-8") != plan["markdown"]:
        raise portable.WorkflowError(
            "stable MR publication does not match this plan; prepare again"
        )
    for request in plan["requests"]:
        path = portable.regular_file(
            root / "artifacts" / "mr_requests" / request["name"], "MR request"
        )
        if (
            path.read_bytes() != request["content"].encode()
            or hashlib.sha256(path.read_bytes()).hexdigest() != request["sha256"]
        ):
            raise portable.WorkflowError("MR request body does not match the plan")
