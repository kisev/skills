#!/usr/bin/env python3
"""Coordinate isolated attempts through explicitly configured adapters."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shlex
import subprocess
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
from portable_runtime.contract import ContractArgumentParser, emit_escalation, report_error
from portable_runtime.state import StateError, atomic_write_json, read_json, revision, skill_state_root

SCHEMA_VERSION = 1
TERMINAL = {"complete", "failed", "cancelled", "blocked", "incomplete", "incomparable"}
FORBIDDEN = {"transcript", "transcripts", "outputs", "reasoning", "diff"}


class MultiRunError(ValueError):
    def __init__(self, message: str, code: str = "multi_run_error") -> None:
        super().__init__(message)
        self.code = code


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def root() -> Path:
    return skill_state_root("multi-run")


def invoke(variable: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    command = os.environ.get(variable)
    if not command:
        return None
    try:
        result = subprocess.run(shlex.split(command), input=json.dumps(payload), text=True, capture_output=True, timeout=120, check=False)
        if result.returncode:
            raise MultiRunError(result.stderr.strip() or f"{variable} failed", "adapter_failed")
        value = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        raise MultiRunError(str(error), "adapter_failed") from error
    if not isinstance(value, dict):
        raise MultiRunError(f"{variable} returned non-object JSON", "adapter_invalid")
    return value


def state_path(identifier: str) -> Path:
    if not identifier or "/" in identifier or "\\" in identifier:
        raise MultiRunError("invalid multi-run id", "invalid_id")
    return root() / f"{identifier}.json"


def confirmation_path(identifier: str) -> Path:
    return root() / "confirmations" / f"{identifier}.json"


def read_file(path: str | None, label: str) -> bytes:
    if not path:
        return b""
    item = Path(path).expanduser().resolve()
    if item.is_symlink() or not item.is_file():
        raise MultiRunError(f"{label} must be a regular file", "invalid_input")
    return item.read_bytes()


def write(path: Path, value: dict[str, Any]) -> None:
    atomic_write_json(path, root(), value)


def issue(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    identifier = uuid.uuid4().hex
    record = {"schema_version": SCHEMA_VERSION, "kind": kind, "confirmation_id": identifier, "payload": payload, "payload_digest": revision(payload), "expires_at": int(time.time()) + 900, "consumed": False}
    write(confirmation_path(identifier), record)
    return record


def consume(identifier: str, digest: str, kind: str) -> dict[str, Any]:
    record = read_json(confirmation_path(identifier), root())
    if record.get("kind") != kind or record.get("payload_digest") != digest or digest != revision(record.get("payload")):
        raise MultiRunError("confirmation digest mismatch", "digest_mismatch")
    if int(record.get("expires_at", 0)) < int(time.time()):
        raise MultiRunError("confirmation expired", "confirmation_expired")
    return record


def check_runs(payload: dict[str, Any], runs: Any) -> list[dict[str, Any]]:
    if not isinstance(runs, list) or len(runs) != payload["count"]:
        raise MultiRunError("attempt adapter did not return every run", "adapter_invalid")
    unique: dict[str, set[Any]] = {key: set() for key in ("run_id", "attempt_id", "session_id", "workspace_id")}
    result: list[dict[str, Any]] = []
    for item in runs:
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key] for key in unique):
            raise MultiRunError("attempt adapter returned incomplete identifiers", "adapter_invalid")
        if item.get("status") not in {"queued", "running"} or FORBIDDEN & item.keys():
            raise MultiRunError("new run violates non-terminal boundary", "adapter_invalid")
        for key, values in unique.items():
            if item[key] in values:
                raise MultiRunError("attempt adapter returned duplicate identity", "adapter_invalid")
            values.add(item[key])
        result.append(item)
    return result


def preview(args: argparse.Namespace) -> dict[str, Any]:
    if not 2 <= args.count <= 5:
        raise MultiRunError("count must be between 2 and 5", "invalid_count")
    project = Path(args.project).expanduser().resolve()
    if not project.is_dir() or project.is_symlink():
        raise MultiRunError("project must be an existing non-symlink directory", "invalid_project")
    task = read_file(args.task_file, "task file")
    if not task:
        raise MultiRunError("task file must not be empty", "invalid_input")
    routing = invoke("AGENT_SKILLS_ROUTE_API", {"operation": "multi_run_preview", "category": args.category, "count": args.count, "profiles": [value for value in args.profiles.split(",") if value]})
    if routing is None:
        emit_escalation("router_unavailable", {"variable": "AGENT_SKILLS_ROUTE_API"})
    decisions = routing.get("decisions")
    if not isinstance(decisions, list) or len(decisions) < args.count:
        raise MultiRunError("router cannot provide enough independent decisions", "adapter_invalid")
    payload = {"schema_version": SCHEMA_VERSION, "task_b64": base64.b64encode(task).decode(), "task_sha256": hashlib.sha256(task).hexdigest(), "constraints_b64": base64.b64encode(read_file(args.constraints_file, "constraints file")).decode(), "project_root": str(project), "start_ref": args.start_ref, "start_ref_sha256": hashlib.sha256(args.start_ref.encode()).hexdigest(), "count": args.count, "category": args.category, "routing": decisions[:args.count]}
    return {"status": "preview", "confirmation_request": issue("multi-run", payload)}


def apply(args: argparse.Namespace) -> dict[str, Any]:
    record = consume(args.confirmation_id, args.confirmation_digest, "multi-run")
    if record.get("consumed"):
        return {"status": "already_started", "multi_run_id": record.get("multi_run_id")}
    payload = record["payload"]
    adapter = invoke("AGENT_SKILLS_ATTEMPTS_API", {"operation": "create_group", "idempotency_key": record["payload_digest"], "task": payload, "routing": payload["routing"]})
    if adapter is None:
        emit_escalation("attempts_api_unavailable", {"variable": "AGENT_SKILLS_ATTEMPTS_API"})
    runs = check_runs(payload, adapter.get("runs"))
    identifier = "mr-" + hashlib.sha256(f"{record['confirmation_id']}:{record['payload_digest']}".encode()).hexdigest()[:32]
    state = {"schema_version": SCHEMA_VERSION, "multi_run_id": identifier, "project_root": payload["project_root"], "task": {"sha256": payload["task_sha256"], "payload_b64": payload["task_b64"]}, "start_ref": payload["start_ref"], "count": payload["count"], "routing": payload["routing"], "runs": runs, "status": "queued", "created_at": now(), "updated_at": now()}
    write(state_path(identifier), state)
    record["consumed"] = True
    record["multi_run_id"] = identifier
    write(confirmation_path(args.confirmation_id), record)
    return {"status": "started", "multi_run_id": identifier, "state": state}


def load(identifier: str) -> dict[str, Any]:
    item = read_json(state_path(identifier), root())
    if item.get("schema_version") != SCHEMA_VERSION or item.get("multi_run_id") != identifier:
        raise MultiRunError("group has unsupported schema", "unsupported_schema")
    return item


def status(args: argparse.Namespace) -> dict[str, Any]:
    state = load(args.multi_run_id)
    adapter = invoke("AGENT_SKILLS_ATTEMPTS_API", {"operation": "status", "multi_run_id": args.multi_run_id})
    if adapter is None:
        return {"status": "partial", "multi_run_id": args.multi_run_id, "runs": state["runs"], "reason": "attempts adapter unavailable"}
    runs = adapter.get("runs")
    if not isinstance(runs, list):
        raise MultiRunError("attempt adapter returned invalid status", "adapter_invalid")
    for item in runs:
        if not isinstance(item, dict) or item.get("status") not in TERMINAL | {"queued", "running"}:
            raise MultiRunError("attempt adapter returned unknown status", "adapter_invalid")
        if item.get("status") not in TERMINAL and FORBIDDEN & item.keys():
            raise MultiRunError("non-terminal run contains hidden result data", "adapter_invalid")
    state["runs"] = runs
    state["status"] = adapter.get("status", state["status"])
    state["updated_at"] = now()
    write(state_path(args.multi_run_id), state)
    return state


def compare(args: argparse.Namespace) -> dict[str, Any]:
    state = load(args.multi_run_id)
    results = [{"run_id": item.get("run_id"), "status": item.get("status"), "manifest": item.get("manifest")} for item in state.get("runs", []) if isinstance(item, dict) and item.get("status") in TERMINAL and isinstance(item.get("manifest"), dict)]
    return {"status": "comparison", "multi_run_id": args.multi_run_id, "criteria": ["status", "checks", "evidence", "usage"], "results": results, "winner": None}


def fusion_preview(args: argparse.Namespace) -> dict[str, Any]:
    state = load(args.multi_run_id)
    source_ids = [value for value in args.source_run_ids.split(",") if value]
    sources = [item for item in state.get("runs", []) if isinstance(item, dict) and item.get("run_id") in source_ids and item.get("status") in TERMINAL and isinstance(item.get("manifest"), dict)]
    if not source_ids or len(sources) != len(source_ids):
        raise MultiRunError("all fusion sources must be terminal", "sources_not_terminal")
    payload = {"multi_run_id": args.multi_run_id, "source_run_ids": source_ids, "source_digests": [item["manifest"].get("content_sha256") for item in sources], "strengths": args.strengths, "start_ref": state["start_ref"]}
    if not all(isinstance(value, str) and value for value in payload["source_digests"]):
        raise MultiRunError("source manifest lacks content digest", "sources_incomplete")
    return {"status": "preview", "confirmation_request": issue("fusion", payload)}


def fusion_apply(args: argparse.Namespace) -> dict[str, Any]:
    record = consume(args.confirmation_id, args.confirmation_digest, "fusion")
    if record.get("consumed"):
        return {"status": "already_started", "fusion": record.get("result")}
    payload = record["payload"]
    state = load(payload["multi_run_id"])
    current = {item.get("run_id"): item for item in state.get("runs", []) if isinstance(item, dict)}
    if [current.get(identifier, {}).get("manifest", {}).get("content_sha256") for identifier in payload["source_run_ids"]] != payload["source_digests"]:
        raise MultiRunError("source manifests changed after preview", "source_digest_mismatch")
    adapter = invoke("AGENT_SKILLS_ATTEMPTS_API", {"operation": "create_fusion", "idempotency_key": record["payload_digest"], "source": payload})
    if adapter is None:
        emit_escalation("attempts_api_unavailable", {"variable": "AGENT_SKILLS_ATTEMPTS_API"})
    run = adapter.get("run", adapter)
    checked = check_runs({"count": 1}, [run])[0]
    checked.update({"kind": "fusion", "source_run_ids": payload["source_run_ids"], "source_digests": payload["source_digests"]})
    state["runs"].append(checked)
    state["updated_at"] = now()
    write(state_path(payload["multi_run_id"]), state)
    record.update({"consumed": True, "result": checked})
    write(confirmation_path(args.confirmation_id), record)
    return {"status": "started", "fusion": checked}


def cancel_preview(args: argparse.Namespace) -> dict[str, Any]:
    state = load(args.multi_run_id)
    targets = [item for item in state.get("runs", []) if isinstance(item, dict) and item.get("status") not in TERMINAL and (not args.run_id or item.get("run_id") == args.run_id)]
    if args.run_id and not targets:
        raise MultiRunError("run is terminal or missing", "run_not_cancellable")
    payload = {"multi_run_id": args.multi_run_id, "run_id": args.run_id, "state_revision": revision(state), "affected_run_ids": [item.get("run_id") for item in targets]}
    return {"status": "preview", "confirmation_request": issue("multi-run-cancel", payload)}


def cancel_apply(args: argparse.Namespace) -> dict[str, Any]:
    record = consume(args.confirmation_id, args.confirmation_digest, "multi-run-cancel")
    if record.get("consumed"):
        return {"status": "already_cancelled"}
    payload = record["payload"]
    state = load(payload["multi_run_id"])
    if revision(state) != payload["state_revision"]:
        raise MultiRunError("cancel preview is stale", "stale_revision")
    results = []
    for run_id in payload["affected_run_ids"]:
        response = invoke("AGENT_SKILLS_ATTEMPTS_API", {"operation": "cancel", "multi_run_id": payload["multi_run_id"], "run_id": run_id})
        if response is None:
            emit_escalation("attempts_api_unavailable", {"variable": "AGENT_SKILLS_ATTEMPTS_API"})
        results.append(response)
    record["consumed"] = True
    write(confirmation_path(args.confirmation_id), record)
    return {"status": "cancel_requested", "results": results}


def parser() -> argparse.ArgumentParser:
    result = ContractArgumentParser(prog="multi-run")
    result.add_argument("--capabilities", action="store_true", help=argparse.SUPPRESS)
    commands = result.add_subparsers(dest="command", required=True)
    item = commands.add_parser("preview")
    item.add_argument("--task-file", required=True)
    item.add_argument("--constraints-file")
    item.add_argument("--project", required=True)
    item.add_argument("--start-ref", required=True)
    item.add_argument("--count", type=int, required=True)
    item.add_argument("--category", default="implementation")
    item.add_argument("--profiles", default="")
    item.set_defaults(handler=preview)
    item = commands.add_parser("apply")
    item.add_argument("--confirmation-id", required=True)
    item.add_argument("--confirmation-digest", required=True)
    item.set_defaults(handler=apply)
    for name, handler in (("status", status), ("compare", compare)):
        item = commands.add_parser(name)
        item.add_argument("--multi-run-id", required=True)
        item.set_defaults(handler=handler)
    item = commands.add_parser("fusion-preview")
    item.add_argument("--multi-run-id", required=True)
    item.add_argument("--source-run-ids", required=True)
    item.add_argument("--strengths", required=True)
    item.set_defaults(handler=fusion_preview)
    item = commands.add_parser("fusion-apply")
    item.add_argument("--confirmation-id", required=True)
    item.add_argument("--confirmation-digest", required=True)
    item.set_defaults(handler=fusion_apply)
    item = commands.add_parser("cancel-preview")
    item.add_argument("--multi-run-id", required=True)
    item.add_argument("--run-id")
    item.set_defaults(handler=cancel_preview)
    item = commands.add_parser("cancel-apply")
    item.add_argument("--confirmation-id", required=True)
    item.add_argument("--confirmation-digest", required=True)
    item.set_defaults(handler=cancel_apply)
    return result


def main(argv: list[str] | None = None) -> int:
    cli = parser()
    if emit_capabilities(argv, cli, payload_version="1.0.0", mutation="write", supports_dry_run=False, confirmation=True, destructive_flags=("--confirmation-id", "--confirmation-digest")):
        return 0
    try:
        args = cli.parse_args(argv)
        print(json.dumps(args.handler(args), ensure_ascii=False, sort_keys=True))
        return 0
    except (MultiRunError, StateError, OSError) as error:
        report_error(getattr(error, "code", "state_error"), str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
