#!/usr/bin/env python3
"""Manage a session-bound, durable goal without host dependencies."""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def bootstrap() -> None:
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))


bootstrap()
from portable_runtime.capabilities import emit_capabilities
from portable_runtime.contract import ContractArgumentParser, report_error
from portable_runtime.state import StateError, atomic_write_json, read_json, revision, skill_state_root

SCHEMA_VERSION = 1
TERMINAL = {"complete", "blocked"}


class GoalError(ValueError):
    def __init__(self, message: str, code: str = "goal_error") -> None:
        super().__init__(message)
        self.code = code


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def root() -> Path:
    return skill_state_root("goal")


def session(value: str | None) -> str:
    result = (value or os.environ.get("OPENCODE_SESSION_ID") or "").strip()
    if not result or len(result) > 256 or any(ord(char) < 32 for char in result):
        raise GoalError("session is required and must be safe", "invalid_session")
    return result


def goals() -> list[tuple[Path, dict[str, Any]]]:
    if not root().is_dir():
        return []
    result = []
    for path in sorted(root().glob("*.json")):
        try:
            item = read_json(path, root())
        except StateError:
            continue
        if item.get("schema_version") == SCHEMA_VERSION:
            result.append((path, item))
    return result


def goal(goal_id: str) -> tuple[Path, dict[str, Any]]:
    if not goal_id or "/" in goal_id or "\\" in goal_id:
        raise GoalError("invalid goal id", "invalid_goal")
    path = root() / f"{goal_id}.json"
    item = read_json(path, root())
    if item.get("schema_version") != SCHEMA_VERSION or item.get("goal_id") != goal_id:
        raise GoalError("goal has unsupported schema", "unsupported_schema")
    return path, item


def write(path: Path, value: dict[str, Any]) -> None:
    atomic_write_json(path, root(), value)


def add_receipt(item: dict[str, Any], status: str, note: str) -> None:
    item["status"] = status
    item["revision"] = int(item.get("revision", 0)) + 1
    item["updated_at"] = now()
    item.setdefault("receipts", []).append({"revision": item["revision"], "status": status, "note": note[:1000], "at": item["updated_at"]})


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    bound = session(args.session)
    if any(item.get("session_id") == bound and item.get("status") not in TERMINAL for _, item in goals()):
        raise GoalError("an active goal is already bound to this session", "session_bound")
    objective = args.objective.strip()
    if not objective or len(objective) > 16_000:
        raise GoalError("objective must be between 1 and 16000 characters", "invalid_objective")
    project = Path(os.environ.get("OPENCODE_PROJECT_ROOT") or os.getcwd()).expanduser().resolve()
    identifier = uuid.uuid4().hex
    item: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "goal_id": identifier,
        "session_id": bound,
        "project_root": str(project) if project.is_dir() else "",
        "status": "paused",
        "revision": 0,
        "objective": objective,
        "completion_criteria": args.completion_criteria.strip(),
        "constraints": args.constraints.strip(),
        "boundaries": args.boundaries.strip(),
        "limits": {"turn_cap": args.turn_cap, "token_budget": args.token_budget},
        "usage": {"turns": 0, "tokens": 0},
        "created_at": now(),
        "updated_at": now(),
        "receipts": [{"revision": 0, "status": "paused", "note": "prepared", "at": now()}],
    }
    if args.turn_cap < 1 or args.token_budget < 0:
        raise GoalError("limits must be positive", "invalid_limits")
    write(root() / f"{identifier}.json", item)
    return item


def transition(args: argparse.Namespace, target: str) -> dict[str, Any]:
    path, item = goal(args.goal_id)
    if item.get("revision") != args.revision:
        raise GoalError("goal revision is stale", "stale_revision")
    expected = "paused" if target == "running" else "running"
    if item.get("status") != expected:
        raise GoalError(f"only a {expected} goal can transition to {target}", "invalid_transition")
    if target == "running" and item.get("session_id") != session(args.session):
        raise GoalError("session does not match goal binding", "session_mismatch")
    add_receipt(item, target, "user transition")
    write(path, item)
    return item


def confirmations() -> dict[str, Any]:
    path = root() / "confirmations.json"
    if not path.exists():
        return {}
    value = read_json(path, root())
    return value if isinstance(value, dict) else {}


def remove(args: argparse.Namespace) -> dict[str, Any]:
    path, item = goal(args.goal_id)
    if item.get("revision") != args.revision:
        raise GoalError("goal revision is stale", "stale_revision")
    payload = {"goal_id": args.goal_id, "revision": args.revision, "record": item}
    digest = revision(payload)
    records = confirmations()
    if args.dry_run:
        identifier = uuid.uuid4().hex
        records[identifier] = {"action": "remove", "digest": digest, "expires_at": int(time.time()) + 600, "consumed": False}
        write(root() / "confirmations.json", records)
        return {"status": "preview", "record": item, "confirmation_request": {"id": identifier, "digest": digest, "expires_at": records[identifier]["expires_at"]}}
    record = records.get(args.confirm_id or "")
    if not isinstance(record, dict) or record.get("action") != "remove":
        raise GoalError("confirmation is unknown", "confirmation_unknown")
    if record.get("consumed") or int(record.get("expires_at", 0)) < int(time.time()):
        raise GoalError("confirmation cannot be used", "confirmation_expired")
    if args.confirm_digest != digest or record.get("digest") != digest:
        raise GoalError("confirmation payload digest mismatch", "digest_mismatch")
    record["consumed"] = True
    write(root() / "confirmations.json", records)
    path.unlink()
    return {"status": "removed", "goal_id": args.goal_id}


def parser() -> argparse.ArgumentParser:
    result = ContractArgumentParser(prog="goal")
    result.add_argument("--capabilities", action="store_true", help=argparse.SUPPRESS)
    commands = result.add_subparsers(dest="command", required=True)
    item = commands.add_parser("prepare")
    item.add_argument("--session")
    item.add_argument("--objective", required=True)
    item.add_argument("--completion-criteria", default="")
    item.add_argument("--constraints", default="")
    item.add_argument("--boundaries", default="")
    item.add_argument("--turn-cap", type=int, default=20)
    item.add_argument("--token-budget", type=int, default=0)
    item.set_defaults(handler=prepare)
    item = commands.add_parser("list")
    item.add_argument("--project")
    item.set_defaults(handler=lambda args: {"schema_version": SCHEMA_VERSION, "goals": [{key: value for key, value in goal_item.items() if key != "constraints"} for _, goal_item in goals() if not args.project or goal_item.get("project_root") == str(Path(args.project).resolve())]})
    item = commands.add_parser("show")
    item.add_argument("--goal-id", required=True)
    item.set_defaults(handler=lambda args: goal(args.goal_id)[1])
    for name, target in (("start", "running"), ("pause", "paused")):
        item = commands.add_parser(name)
        item.add_argument("--goal-id", required=True)
        item.add_argument("--revision", type=int, required=True)
        item.add_argument("--session")
        item.set_defaults(handler=lambda args, target=target: transition(args, target))
    item = commands.add_parser("remove")
    item.add_argument("--goal-id", required=True)
    item.add_argument("--revision", type=int, required=True)
    item.add_argument("--dry-run", action="store_true")
    item.add_argument("--confirm-id")
    item.add_argument("--confirm-digest")
    item.set_defaults(handler=remove)
    return result


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    if emit_capabilities(argv, cli, payload_version="1.0.0", mutation="write", supports_dry_run=True, confirmation=True, destructive_flags=("--confirm-id", "--confirm-digest")):
        return 0
    try:
        args = cli.parse_args(argv)
        print(__import__("json").dumps(args.handler(args), ensure_ascii=False, sort_keys=True))
        return 0
    except (GoalError, StateError, OSError) as error:
        report_error(getattr(error, "code", "state_error"), str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
