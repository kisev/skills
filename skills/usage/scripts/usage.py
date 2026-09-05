#!/usr/bin/env python3
"""Build a strictly read-only local usage ledger."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

scripts = Path(__file__).resolve().parent
if str(scripts) not in sys.path:
    sys.path.insert(0, str(scripts))

from portable_runtime.capabilities import emit_capabilities
from portable_runtime.contract import ContractArgumentParser, report_error
from portable_runtime.state import StateError, read_json, skill_state_root


def instant(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def component(name: str, paths: list[str], errors: list[dict[str, str]]) -> dict[str, Any]:
    return {"name": name, "status": "partial" if errors else "ok", "source_paths": paths, "errors": errors}


def goals(project: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = skill_state_root("goal")
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    paths: list[str] = []
    if not root.is_dir() or root.is_symlink():
        return items, component("goal", [str(root)], errors)
    for path in sorted(root.glob("*.json")):
        paths.append(str(path))
        try:
            value = read_json(path, root)
            if value.get("schema_version") != 1 or not isinstance(value.get("session_id"), str):
                raise StateError("unsupported goal schema or session identity")
            if project and value.get("project_root") not in {"", project}:
                continue
            items.append({"kind": "goal", "id": value.get("goal_id"), "label": value.get("objective", "goal"), "session_id": value["session_id"], "period_start": value.get("created_at", ""), "period_end": value.get("updated_at", ""), "state_tokens": value.get("usage", {}).get("tokens") if isinstance(value.get("usage"), dict) else None})
        except StateError as error:
            errors.append({"path": str(path), "error": str(error)})
    return items, component("goal", paths, errors)


def scheduled(project: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    import hashlib

    root = skill_state_root("schedule") / hashlib.sha256(project.encode()).hexdigest()
    receipt = root / "receipts.jsonl"
    items: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    if receipt.is_file() and not receipt.is_symlink():
        try:
            for number, line in enumerate(receipt.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict) or not isinstance(value.get("run_id"), str) or not isinstance(value.get("session_id"), str):
                    raise ValueError("receipt lacks run/session identity")
                items[value["run_id"]] = {"kind": "scheduled_run", "id": value["run_id"], "label": value.get("task_id", "scheduled run"), "session_id": value["session_id"], "period_start": value.get("started_at", ""), "period_end": value.get("finished_at", value.get("started_at", ""))}
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
            errors.append({"path": str(receipt), "error": str(error)})
    return list(items.values()), component("schedule", [str(receipt)], errors)


def messages(session_ids: set[str], since: datetime | None) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "opencode" / "storage" / "message"
    result: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    paths: list[str] = []
    for session_id in sorted(session_ids):
        total: dict[str, Any] = {"turns": 0, "tokens": 0, "cost": 0.0, "cost_observations": 0}
        directory = base / session_id
        if not directory.is_dir() or directory.is_symlink():
            result[session_id] = total
            continue
        for path in sorted(directory.glob("*.json")):
            paths.append(str(path))
            try:
                if path.is_symlink():
                    raise ValueError("message is a symlink")
                value = json.loads(path.read_text(encoding="utf-8"))
                info = value.get("info", value) if isinstance(value, dict) else {}
                if not isinstance(info, dict) or info.get("role") != "assistant":
                    continue
                created = instant((info.get("time") or {}).get("created") if isinstance(info.get("time"), dict) else info.get("created_at"))
                if since and created and created < since:
                    continue
                tokens = info.get("tokens") if isinstance(info.get("tokens"), dict) else {}
                total["turns"] += 1
                total["tokens"] += int(tokens.get("total", tokens.get("output", 0)) or 0)
                cost = info.get("cost")
                if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0:
                    total["cost"] += float(cost)
                    total["cost_observations"] += 1
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
                errors.append({"path": str(path), "error": str(error)})
        result[session_id] = total
    return result, component("opencode_messages", paths, errors)


def report(args: argparse.Namespace) -> dict[str, Any]:
    project = str(Path(args.project or os.environ.get("OPENCODE_PROJECT_ROOT") or os.getcwd()).expanduser().resolve())
    since = instant(args.since)
    if args.since and since is None:
        raise ValueError("since must be ISO8601")
    work, goal_component = goals(project)
    runs, schedule_component = scheduled(project)
    work.extend(runs)
    observed, message_component = messages({str(item["session_id"]) for item in work}, since)
    for item in work:
        usage = observed.get(str(item["session_id"]), {"turns": 0, "tokens": 0, "cost": 0.0, "cost_observations": 0})
        item["usage"] = {"turns": usage["turns"], "tokens": usage["tokens"]}
        item["cost"] = usage["cost"] if usage["turns"] == usage["cost_observations"] else None
        item["cost_status"] = "known" if item["cost"] is not None else "unknown"
        if item["kind"] == "goal" and isinstance(item.get("state_tokens"), int):
            item["reconciliation"] = {"state_tokens": item["state_tokens"], "ledger_tokens": usage["tokens"], "delta": usage["tokens"] - item["state_tokens"], "status": "match" if usage["tokens"] == item["state_tokens"] else "mismatch"}
    return {"schema_version": 1, "project": project, "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"), "components": [goal_component, schedule_component, message_component], "work_items": sorted(work, key=lambda item: (str(item["kind"]), str(item["id"]))) }


def parser() -> argparse.ArgumentParser:
    result = ContractArgumentParser(prog="usage")
    result.add_argument("--capabilities", action="store_true", help=argparse.SUPPRESS)
    result.add_argument("--since")
    result.add_argument("--project")
    result.add_argument("--format", choices=("json", "text", "both"), default="both")
    return result


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    if emit_capabilities(argv, cli, payload_version="1.0.0", mutation="read", supports_dry_run=False):
        return 0
    try:
        args = cli.parse_args(argv)
        value = report(args)
    except ValueError as error:
        report_error("invalid_arguments", str(error))
        return 2
    text = "\n".join(f"{item['kind']} {item['label']}: {item['usage']['tokens']} tokens, {item['cost_status']} cost" for item in value["work_items"]) or "No usage records."
    if args.format in {"json", "both"}:
        print(json.dumps({**value, "text": text}, ensure_ascii=False, sort_keys=True))
    if args.format in {"text", "both"}:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
