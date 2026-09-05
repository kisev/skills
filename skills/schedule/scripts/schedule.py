#!/usr/bin/env python3
"""Manage explicit, disabled-by-default scheduler definitions."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

scripts = Path(__file__).resolve().parent
if str(scripts) not in sys.path:
    sys.path.insert(0, str(scripts))

from portable_runtime.capabilities import emit_capabilities
from portable_runtime.contract import ContractArgumentParser, report_error
from portable_runtime.state import StateError, atomic_write_json, read_json, revision, skill_state_root

ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
EVERY = re.compile(r"^every:\s*\d+\s*[smhd]$", re.I)
CRON = re.compile(r"^cron:\s*(?:\S+\s+){4}\S+$", re.I)
SCHEMA_VERSION = 1


class ScheduleError(ValueError):
    def __init__(self, message: str, code: str = "schedule_error") -> None:
        super().__init__(message)
        self.code = code


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def project(value: str | None) -> Path:
    result = Path(value or os.environ.get("OPENCODE_PROJECT_ROOT") or os.getcwd()).expanduser().resolve()
    if not result.is_dir() or result.is_symlink():
        raise ScheduleError("project must be an existing non-symlink directory", "invalid_project")
    return result


def state_root(root: Path) -> Path:
    return skill_state_root("schedule") / hashlib.sha256(str(root).encode()).hexdigest()


def definition_path(root: Path, identifier: str) -> Path:
    return state_root(root) / "definitions" / f"{identifier}.json"


def confirmation_path(root: Path, identifier: str) -> Path:
    return state_root(root) / "confirmations" / f"{identifier}.json"


def validate(item: dict[str, Any]) -> dict[str, Any]:
    required = {"id", "name", "schedule", "agent", "model", "run_as_goal", "token_budget", "max_runtime", "prompt"}
    if item.get("schema_version") != SCHEMA_VERSION or not required <= item.keys():
        raise ScheduleError("definition has unsupported schema", "unsupported_schema")
    if not isinstance(item["id"], str) or not ID.fullmatch(item["id"]):
        raise ScheduleError("definition id is invalid", "invalid_definition")
    if not all(isinstance(item[key], str) and item[key].strip() for key in ("name", "agent", "model", "prompt")):
        raise ScheduleError("definition text fields are invalid", "invalid_definition")
    if not isinstance(item["schedule"], str) or not (EVERY.fullmatch(item["schedule"].strip()) or CRON.fullmatch(item["schedule"].strip())):
        raise ScheduleError("definition schedule is invalid", "invalid_definition")
    if type(item["run_as_goal"]) is not bool or type(item["token_budget"]) is not int or item["token_budget"] < 0 or type(item["max_runtime"]) is not int or item["max_runtime"] <= 0:
        raise ScheduleError("definition limits are invalid", "invalid_definition")
    return {**item, "enabled": item.get("enabled") is True}


def managed(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    directory = state_root(root) / "definitions"
    values: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    if not directory.is_dir():
        return values, errors
    for path in sorted(directory.glob("*.json")):
        try:
            value = validate(read_json(path, state_root(root)))
            values.append({**value, "path": str(path), "source": "managed"})
        except (ScheduleError, StateError) as error:
            errors.append({"path": str(path), "error": str(error)})
    return values, errors


def markdown(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ScheduleError("definition is not a regular file")
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---" or "---" not in lines[1:]:
        raise ScheduleError("definition has no flat frontmatter")
    end = lines.index("---", 1)
    value: dict[str, Any] = {"schema_version": SCHEMA_VERSION}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line or line.startswith((" ", "\t")):
            raise ScheduleError("frontmatter is not flat")
        key, raw = line.split(":", 1)
        text = raw.strip().strip("'\"")
        value[key.strip()] = {"true": True, "false": False}.get(text, int(text) if text.isdecimal() else text)
    value["prompt"] = "\n".join(lines[end + 1:]).strip()
    return validate(value)


def definitions(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    result, errors = managed(root)
    by_id = {item["id"]: item for item in result}
    current = root
    while True:
        loops = current / ".agents" / "loops"
        if loops.is_dir() and not loops.is_symlink():
            for path in sorted(loops.glob("*.md")):
                try:
                    item = markdown(path)
                    by_id.setdefault(item["id"], {**item, "path": str(path), "source": "project"})
                except (OSError, ScheduleError) as error:
                    errors.append({"path": str(path), "error": str(error)})
        if current.parent == current:
            break
        current = current.parent
    return sorted(by_id.values(), key=lambda value: value["id"]), errors


def preview(root: Path, action: str, target: str, payload: dict[str, Any]) -> dict[str, Any]:
    identifier = uuid.uuid4().hex
    request = {"id": identifier, "action": action, "target": target, "digest": revision(payload), "expires_at": int(time.time()) + 600, "consumed": False}
    atomic_write_json(confirmation_path(root, identifier), state_root(root), {"request": request, "payload": payload})
    return {"status": "preview", "confirmation_request": {key: request[key] for key in ("id", "action", "target", "digest", "expires_at")}, "payload": payload}


def confirm(root: Path, identifier: str | None, payload: dict[str, Any]) -> None:
    if not identifier:
        raise ScheduleError("confirmation id is required", "confirmation_unknown")
    path = confirmation_path(root, identifier)
    record = read_json(path, state_root(root))
    request = record.get("request")
    if not isinstance(request, dict) or request.get("consumed") is True:
        raise ScheduleError("confirmation was already used", "confirmation_consumed")
    if int(request.get("expires_at", 0)) < int(time.time()):
        raise ScheduleError("confirmation expired", "confirmation_expired")
    if request.get("digest") != revision(payload) or record.get("payload") != payload:
        raise ScheduleError("confirmation payload changed", "digest_mismatch")
    request["consumed"] = True
    atomic_write_json(path, state_root(root), record)


def change(args: argparse.Namespace) -> dict[str, Any]:
    root = project(args.project)
    if not ID.fullmatch(args.id):
        raise ScheduleError("invalid id", "invalid_definition")
    target = definition_path(root, args.id)
    if args.command == "add":
        definition = validate({"schema_version": SCHEMA_VERSION, "id": args.id, "name": args.name, "schedule": args.schedule, "agent": args.agent, "model": args.model, "run_as_goal": args.run_as_goal, "token_budget": args.token_budget, "max_runtime": args.max_runtime, "prompt": args.prompt, "enabled": False})
        payload = {"operation": "add", "target": str(target), "definition": definition}
        if not args.confirmation_id:
            if target.exists() or any(item["id"] == args.id for item in definitions(root)[0]):
                raise ScheduleError("definition already exists", "already_exists")
            return preview(root, "add", str(target), payload)
        confirm(root, args.confirmation_id, payload)
        if target.exists() or any(item["id"] == args.id for item in definitions(root)[0]):
            raise ScheduleError("definition changed after preview", "stale_revision")
        atomic_write_json(target, state_root(root), definition)
        return {"status": "applied", "definition": definition}
    current = validate(read_json(target, state_root(root)))
    desired = None if args.command == "remove" else {**current, "enabled": args.command == "enable"}
    payload = {"operation": args.command, "target": str(target), "revision": revision(current), "definition": desired}
    if not args.confirmation_id:
        return preview(root, args.command, str(target), payload)
    confirm(root, args.confirmation_id, payload)
    if revision(validate(read_json(target, state_root(root)))) != payload["revision"]:
        raise ScheduleError("definition changed after preview", "stale_revision")
    if desired is None:
        target.unlink()
        return {"status": "applied", "removed": args.id}
    atomic_write_json(target, state_root(root), desired)
    return {"status": "applied", "definition": desired}


def parser() -> argparse.ArgumentParser:
    result = ContractArgumentParser(prog="schedule")
    result.add_argument("--capabilities", action="store_true", help=argparse.SUPPRESS)
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("list", "status"):
        item = commands.add_parser(name)
        item.add_argument("--project")
        item.set_defaults(handler=lambda args: {"schema_version": SCHEMA_VERSION, "definitions": definitions(project(args.project))[0], "errors": definitions(project(args.project))[1], "at": now()})
    item = commands.add_parser("add")
    item.add_argument("--project")
    item.add_argument("--id", required=True)
    item.add_argument("--name", required=True)
    item.add_argument("--schedule", required=True)
    item.add_argument("--agent", required=True)
    item.add_argument("--model", required=True)
    item.add_argument("--prompt", required=True)
    item.add_argument("--run-as-goal", action="store_true")
    item.add_argument("--token-budget", type=int, default=0)
    item.add_argument("--max-runtime", type=int, default=3600)
    item.add_argument("--confirmation-id")
    item.set_defaults(handler=change)
    for name in ("enable", "disable", "remove"):
        item = commands.add_parser(name)
        item.add_argument("--project")
        item.add_argument("--id", required=True)
        item.add_argument("--confirmation-id")
        item.set_defaults(handler=change)
    return result


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    if emit_capabilities(argv, cli, payload_version="1.0.0", mutation="write", supports_dry_run=False, confirmation=True, destructive_flags=("--confirmation-id",)):
        return 0
    try:
        args = cli.parse_args(argv)
        print(json.dumps(args.handler(args), ensure_ascii=False, sort_keys=True))
        return 0
    except (ScheduleError, StateError, OSError) as error:
        report_error(getattr(error, "code", "state_error"), str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
